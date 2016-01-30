Writing Tasks
=============

The definitive guide to writing pytask tasks. The first step is to name your task, like so:

.. code:: python

    class MyTask(Task):
        NAME = 'mytask'

It is recommended to namespace your names, for example the ``Monitor`` and ``Cleanup``
tasks included with pytask are named ``pytask/monitor`` and ``pytask/cleanup``
respectively.


Data & Init
-----------

Tasks should define an ``__init__`` function which will be passed task data as kwargs.
Remember task data is defined in JSON, so you'll need to handle non-JSON-serializable
objects.

.. code:: python

    class MyTask(Task):
        def __init__(self, my_task_option='default'):
            self.option = my_task_option


Start & Stop
------------

Tasks *must* implement a ``.start`` method, this is called directly in a greenlet to start
and execute the task. When this function ends the task is considered to be ended.

.. code:: python

    class MyTask(Task):
        ...
        def start(self):
            do_some_work()

This works well for short lived tasks, but sometimes we want to run something which runs
forever/a-long-time. To achieve this we can use a separate greenlet and the ``.stop``
method to gracefully handle shutdown:

.. code:: python

    class MyTask(Task):
        ...
        def start(self):
            self.loop = gevent.spawn(self.work)
            self.loop.get()

        def stop(self):
            self.loop.kill()

        def work(self):
            do_some_work()


Emitting Events
---------------

Tasks can emit events to Redis pubsub:

.. code:: python

    class MyTask(Task):
        ...
        def start(self):
            self.emit('event-name', {'some': 'data'})


Handling Errors
---------------

When tasks encounter an error, they should raise a ``self.Error`` exception. This will
put them into ``ERROR`` state - crucially different to ``EXCEPTION`` which is reserved
for unexpected errors.

.. code:: python

    class MyTask(Task):
        ...
        def start(self):
            raise self.Error('Task failz!')


Context
-------

Sometimes it's desirable to wrap task method calls with some kind of application specific
context (eg a Flask app). To do this a task needs to define a static ``provide_context``
method, like so:

.. code:: python

    class MyTask(Task):
        @staticmethod
        def provide_context():
            # Wrap task methods in Flask.app_context
            return web_app.app_context()

The context will be created before the task instance is created, and all task methods
(``__init__``, ``start`` & ``stop``) will be nested inside the context.
