# Redis-Model

Redis-Model is a Python [ORM](http://en.wikipedia.org/wiki/Object-relational_mapping) for [Redis](http://redis.io) database.

## Getting started

Before you start, you need to install the following packages:

- [redis-py](https://github.com/andymccurdy/redis-py)

For the current release of Redis-Model, installation using <i>easy_install</i> or <i>pip</i> is not supported.
You can simply copy <b>redis_model</b> directory under your project directory. That's all!

## Tutorial

### Model definition

Let's define your first model, User:

<pre class="python-code">
from redis_model import Model, Property

class User(Model):
    username = Property(unique=True)
    display_name = Property(default_value='I have no name yet.')
    email = Property()
</pre>

As simple as it seems. 
We just defined the <b>User</b> model which has 3 properties: <i>username</i>, <i>display_name</i>, and <i>email</i>. 

- <i>username</i> is declared as <b>unique</b>. The value of this property must be unique in the database.
- <i>display_name</i> have default value. When you do not assign the value of this property, this default value will be stored.
- <i>email</i> property is not unique and do not have any default values. If you don't assign any value, it will have <i>None</i> as its value.

### Storing

Now, let me create a User instance, and store it to the database:

<pre class="python-code">
u1 = User()
u1.username = 'Daniel'
u1.email = 'me@example.com'
u1.put()
</pre>

<i>put()</i> function simply store the current object to the database. In this case, we've just created a new User instance.

But, modifying (update) is easy as well:

<pre class="python-code">
u1.username = 'Daniel Kang'
u1.display_name = 'Daniel Kang'
u1.put()
</pre>

I changed the value of <i>username</i> and <i>display_name</i> properties, and then, called <i>put()</i> function again on the same object.
This will simply modify (or, update) our database instance using the same function, <i>put()</i>.

This time, I'd like to exploit the flexibility of Python language:

<pre class="python-code">
u1.age = 29
u1.memo = 'Hello, World!'
u1.put()
</pre>

Once again, I called <i>put()</i> function.
But, this time, I added 2 new properties: <i>age</i> and <i>memo</i>, which are not stated in our User class.

I'd like to call these properties as <b>dynamic properties</b>. 
Using Python language's syntactic flexibility, you can freely add, remove, or update any properties.
And, this is the one of the reason why we use [NoSQL](http://en.wikipedia.org/wiki/NoSQL) databases.

### Retrieving

We can load our instances from the database using <i>get()</i> function:

<pre class="python-code">
daniel = User.get(3983)
jack = User.get(username='jack')
</pre>

I've just loaded 2 User instances from the database.

- <i>daniel</i> instance was retrieved using its model-id.
- <i>jack</i> instance was retrieved using its username property.

Whenever you create a new instance, each instance have a unique numeric id, <i>model-id</i>. 
You can get the model-id using <i>model_id()</i> function of your model object. 
The model-id won't be changed even if you update the model using <i>put()</i> function.

And, you can also get the model instance using their unique properties. 
Since we declared <i>username</i> as unique, we can get an instance using a value of username.

### Deleting

To delete an instance from the database, you can just call <i>delete()</i> function of the model object.

<pre class="python-code">
daniel.delete()       # RIP!
</pre>

## More options

In the above tutorial, I intentionally skipped many details.

### Database connection

If you don't specify any database connection parameters explicitly,
<i>redis-model</i> implementation will try to connect the Redis server running on the localhost:3679.

But, you can change it using a special decorator, <i>Model.Config</i>:

<pre class="python-code">
@Model.Config(db={'host':'12.51.55.143', 'port':3333, 'db': 0})
class User(Model):
    # ...
</pre>

These parameters are directly passed to <i>__init__()</i> function of StrictRedis class of [redis-py](https://github.com/andymccurdy/redis-py).

Or, you can have more flexibility for <i>db</i> argument:

<pre class="python-code">
@Model.Config(db=get_my_db_client)
class User(Model):
    # ...
</pre>

In this case, I used an identifer named <i>get_my_db_client</i>. This can be function name, class name, or object name. 
Any callable object will be accepted. Additionally, you can even use lambda expression:

<pre class="python-code">
@Model.Config(db=lambda: my_db_client)
class User(Model):
    # ...
</pre>

If you provide any callable element to <i>db</i> argument, 
whenever you call database functions for the model (<i>get()</i>, <i>put()</i>, or <i>delete()</i>),
your callable thing will be invoked, and your callable must return a valid StrictRedis object.

When invoked, your callable can have zero or one parameter, <i>cls</i>: class object of the model. Let me write one simple example callable:

<pre class="python-code">
class get_my_db_client(object):
    def __init__(self):
        # ....
        
    def __call__(self, model_cls):
        # In our tutorial example, model_cls will be User.
        return my_db_client
</pre>

As said eariler, you can use either a class name or an object name. 
In case you provide an object, that very object will be used whenever the database client is needed.
However, if you just provide the class name, a new object of that class will be created and then used.

Your callable will be invoked just once at the beginning of each database functions (<i>get()</i>, <i>put()</i>, or <i>delete()</i>).
So you can assume that the number of invocation will be the number of database function calls.

### Model name

By default, when storing your model objects, the name of the class (<i>User</i> in the tutorial) will be used as a model-name.
However, you can also use different names using <i>model_name</i> argument to <i>Model.Config</i> decorator:

<pre class="python-code">
@Model.Config(model_name='user_model', db=lambda: my_db_client)
class User(Model):
    # ...
</pre>

### Debug mode

For debugging purpose, you can enable debug mode for the model using <i>debug_mode</i> argument to <i>Model.Config</i> decorator:

<pre class="python-code">
@Model.Config(debug_mode=True, db=lambda: my_db_client)
class User(Model):
    # ...
</pre>

Debug mode is disabled by default.

## API references

... will be updated soon.