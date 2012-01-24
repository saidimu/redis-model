import re
import types
try: import simplejson as json
except ImportError: import json
from redis import StrictRedis, WatchError

# {model_name}:mid - next model id to allocate
# {model_name}:{model_id} - JSON serializaed object
# {model_name}:{model_id}:rks - reverse key set
# {model_name}:{reverse_key_name}:{reverse_key_value} - reverse key to model id

class UniquePropertyException(Exception):
    def __init__(self, property_name, message=None):
        self.property_name = property_name
        self.message = message or 'Unique property exception: '+property_name

class DatabaseClientException(Exception):
    def __init__(self, message=None):
        self.message = message or 'Database client is required.'

def _check_model_name(model_name):
    if model_name is None:
        return False

    # 1. start with alphabet
    # 2. only contains alphabet, numbers, underline
    if not re.match('^[A-Za-z][A-Za-z0-9_]*$', model_name):
        return False

    return True

def _check_prop_name(prop_name):
    if prop_name is None:
        return False

    # 1. start with alphabet or underline
    # 2. only contains alphabet, numbers, underline
    if not re.match('^[A-Za-z_][A-Za-z0-9_]*$', prop_name):
        return False

    return True

def _is_storable_prop_name(prop_name):
    if not _check_prop_name(prop_name):
        return False
    
    if prop_name[0] == '_':
        return False

    return True

class Property(object):
    def __init__(self, unique=False, default_value=None):
        self._unique = unique
        self._default_value = default_value

    def unique(self):
        return self._unique

    def default_value(self):
        return self._default_value

class Model(object):
    class _meta(type):
        def __new__(meta, classname, bases, class_dict):
            if 'object' in bases:
                raise TypeError('You cannot instantiate the Model class.')

            new_type = type.__new__(meta, classname, bases, class_dict)

            # static validation for static properties
            prop_names = set()
            static_props = [(k, v) for k, v in new_type.__dict__.iteritems() if isinstance(v, Property)]
            for k, v in static_props:
                # check for duplicate property names
                if k in prop_names:
                    raise TypeError('Duplicate property name: '+classname+'.'+k)
                else:
                    prop_names.add(k)

                # test the property naming rules
                if not _check_prop_name(k):
                    raise TypeError('Invalid property name: '+classname+'.'+k)
            
            return new_type
    

    class Config(object):
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __call__(self, cls):
            # model_name
            cls._model_name = self.kwargs.pop('model_name', None) or cls.__name__
            if not _check_model_name(cls._model_name):
                raise TypeError('Invalid model name: '+cls._model_name)

            # debug mode
            cls._debug_mode = bool(self.kwargs.pop('debug_mode', False))

            # db
            db = self.kwargs.pop('db', None)
            if db is None:
                # use default connection
                cls._db = db
            elif isinstance(db, dict):
                # use connection options
                cls._db = db
            elif isinstance(db, types.FunctionType):
                cls._db = staticmethod(db)
            elif isinstance(db, type):
                if '__call__' in db.__dict__:
                    cls._db = db
                else:
                    raise TypeError('Invalid value type of argument db: '+db.__name__)                
            elif hasattr(db, '__call__'):
                # use callable object
                cls._db = db
            else:
                raise TypeError('Invalid value type of argument db: '+db.__class__.__name__)

            # unrecognized options
            if len(self.kwargs):
                raise TypeError('Unrecognized arguments in ModelContext: '+', '.join(self.kwargs.keys()))

            return cls

    __metaclass__ = _meta

    # intialize Model object
    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls, *args, **kwargs)
        obj._model_id = None
        return obj

    def model_id(self):
        return self._model_id

    def model_name(self):
        return self.__class__._model_name

    @classmethod
    def _is_debug_mode(cls):
        return getattr(cls, '_debug_mode', False)

    @classmethod
    def _get_db(cls):
        if cls._db is None:
            return StrictRedis()

        if isinstance(cls._db, dict):
            # create client with options
            return StrictRedis(**cls._db)
        else:
            # try callable 
            c = None
            if isinstance(cls._db, type):
                c = cls._db()
            else:
                c = cls._db
            # invoke callable object            
            try: return c(cls)
            except TypeError: return c()

    @classmethod
    def get_model_id(cls, **kwargs):
        db = cls._get_db()
        if db is None:
            raise DatabaseClientException()

        if len(kwargs) is not 1:
            raise RuntimeError('Name and value pair of unique property are required.')

        filter_prop_name, filter_prop_value = kwargs.items()[0]
        for k, v in cls.__dict__.iteritems():
            if filter_prop_name == k:
                return db.get('{0}:{1}:{2}'.format(cls._model_name, filter_prop_name, filter_prop_value))
        
        raise RuntimeError('Filtering property is not a unique property: '+filter_prop_name)

    # return a list of static property tuples: (propery_name, property_desc, property_value).
    # unassigned static members are not stored.    
    def _get_static_props(self):        
        static_props = []        
        for k, d in self.__class__.__dict__.iteritems():            
            if isinstance(d, Property):                
                if k in self.__dict__:
                    # if k has a value, use that value (even if it's None).
                    static_props.append((k, d, self.__dict__[k]))
                else:
                    # otherwise, use default value defined in descriptor.
                    static_props.append((k, d, d.default_value()))        
        return static_props

    # return a list of dynamic property tuple: (propery_name, property_value).
    def _get_dynamic_props(self):
        return [(k, v) 
                for k, v in self.__dict__.iteritems() 
                if (not hasattr(self.__class__, k)) and (v is not None) and _is_storable_prop_name(k)]

    @classmethod
    def get(cls, model_id=None, **kwargs):
        db = cls._get_db()
        if db is None:
            raise DatabaseClientException()

        if model_id is None:
            model_id = cls.get_model_id(**kwargs)
            if model_id is None:
                return None

        # model instance
        model_inst = None
        model_prop_names = None
        model_prop_values = None

        json_text = db.get('{0}:{1}'.format(cls._model_name, model_id))
        if json_text is None:
            return None
        
        json_data = json.loads(json_text)

        # create an instance of model, and reconstruct properties
        model_inst = cls()
        for prop_name, prop_value in json_data.iteritems():
            is_static_prop = False
            for k, v in cls.__dict__.iteritems():
                if isinstance(v, Property):
                    if prop_name == k:
                        setattr(model_inst, prop_name, prop_value)
                        is_static_prop = True
                        break
            if not is_static_prop:
                setattr(model_inst, prop_name, prop_value)
        
        # set model-id attribute
        if model_inst is not None:
            model_inst._model_id = model_id

        return model_inst

    def _insert(self, db):
        # static properties: [(name, desc, value), ...]
        static_props = self._get_static_props()
        # dynamic properties: [(name, value), ...]
        dynamic_props  = self._get_dynamic_props()

        # build content dict and validate properties
        dup_test = set()
        json_data = dict()
        unique_prop_keys = list()
        for k, d, v in static_props:
            # static props are checked for duplication
            #if k in dup_test:
            #    raise TypeError('Duplicate property name: '+model_name+'.'+k)
            dup_test.add(k)
            json_data[k] = v

            if d.unique():
                if v is None:
                    raise ValueError('Unique property cannot be None.')
                unique_prop_keys.append('{0}:{1}:{2}'.format(self.__class__._model_name, k, v))
        for k, v in dynamic_props:
            # test duplication
            if k in dup_test:
                raise TypeError('Duplicate property name: '+self.__class__.__name__+'.'+k)
            # test naming rules
            if not _check_prop_name(k):
                raise TypeError('Invalid property name: '+self.__class__.__name__+'.'+k)
            dup_test.add(k)
            json_data[k] = v
        
        # serialize contents to the JSON string
        json_text = json.dumps(json_data)

        # model-id: allocate new id
        model_id = db.incr('{0}:mid'.format(self.__class__._model_name))

        # key names
        data_key = '{0}:{1}'.format(self.__class__._model_name, model_id)
        rks_key = data_key + ':rks'

        # test for uniqueness
        for k in unique_prop_keys:
            if db.exists(k):        
                raise UniquePropertyException(k.split(':')[1])

        with db.pipeline() as pipe:
            while True:
                try:
                    # start monitoring unique keys
                    if len(unique_prop_keys):
                        pipe.watch(*unique_prop_keys)

                    # test for uniqueness again
                    for k in unique_prop_keys:
                        if pipe.exists(k):        
                            raise UniquePropertyException(k.split(':')[1])
                    
                    # start command buffering
                    pipe.multi()

                    # insert unique props
                    [pipe.set(k, model_id) for k in unique_prop_keys]
                    # insert contents
                    pipe.set(data_key, json_text)
                    # insert rks
                    pipe.sadd(rks_key, *unique_prop_keys)

                    # run them all
                    pipe.execute()

                    # set model-id attribute
                    self._model_id = model_id

                    return True
                except WatchError:
                    # uniqueness broken
                    continue
        
        return False

    def _update(self, db):
        # model name and id
        model_id = self._model_id

        # static properties: [(name, desc, value), ...]
        static_props = self._get_static_props()
        # dynamic properties: [(name, value), ...]
        dynamic_props  = self._get_dynamic_props()

        # build content dict and validate properties
        dup_test = set()
        json_data = dict()
        unique_prop_keys = list()
        for k, d, v in static_props:
            # static props are checked for duplication
            #if k in dup_test:
            #    raise TypeError('Duplicate property name: '+model_name+'.'+k)
            dup_test.add(k)
            json_data[k] = v

            if d.unique():
                if v is None:
                    raise ValueError('Unique property cannot be None.')
                unique_prop_keys.append('{0}:{1}:{2}'.format(self.__class__._model_name, k, v))
        for k, v in dynamic_props:
            # test duplication
            if k in dup_test:
                raise TypeError('Duplicate property name: '+self.__class__.__name__+'.'+k)
            # test naming rules
            if not _check_prop_name(k):
                raise TypeError('Invalid property name: '+self.__class__.__name__+'.'+k)
            dup_test.add(k)
            json_data[k] = v
        
        # serialize contents to the JSON string
        json_text = json.dumps(json_data)
        
        # key names
        data_key = '{0}:{1}'.format(self.__class__._model_name, model_id)
        rks_key = data_key + ':rks'

        with db.pipeline() as pipe:
            while True:
                try:
                    # watch and get rks
                    pipe.watch(rks_key, *unique_prop_keys)
                    rks = pipe.smembers(rks_key)

                    # test for uniqueness: only for new keys
                    for k in unique_prop_keys:
                        if k not in rks and pipe.exists(k):        
                            raise UniquePropertyException(k.split(':')[1])

                    # start command buffering
                    pipe.multi()

                    # update unique props                    
                    pipe.delete(*rks)
                    [pipe.set(k, model_id) for k in unique_prop_keys]
                    # update contents
                    pipe.set(data_key, json_text)
                    # update rks                    
                    pipe.sadd(rks_key, *unique_prop_keys)

                    # run them all
                    pipe.execute()

                    return True
                except WatchError:
                    # uniqueness broken
                    continue
        
        return False

    def put(self):
        db = self._get_db()
        if db is None:
            raise DatabaseClientException()

        if self._model_id is None:
            return self._insert(db)
        else:
            return self._update(db)

    def delete(self):
        db = self._get_db()
        if db is None:
            raise DatabaseClientException()

        if self._model_id is None:
            raise RuntimeError('The object is unsaved or already deleted.')

        # key names
        data_key = '{0}:{1}'.format(self.__class__._model_name, self._model_id)
        rks_key = data_key + ':rks'

        with db.pipeline() as pipe:
            while True:
                try:
                    # watch and get rks
                    pipe.watch(rks_key)
                    rks = pipe.smembers(rks_key)

                    # start command buffering
                    pipe.multi()

                    # delete rerverse keys
                    pipe.delete(*rks)
                    # delete model data
                    pipe.delete(data_key)
                    # delete rks
                    pipe.delete(rks_key)

                    # run them all
                    if self._is_debug_mode():
                        results = pipe.execute()
                        if not all(results):
                            raise RuntimeError('Model delete() failed: '+str(results))
                    else:
                        pipe.execute()
                    
                    self._model_id = None
                    return True
                except WatchError:
                    continue
        
        return False        