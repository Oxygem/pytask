Starting Workers
================

To create a pytask worker you create an instance of ``PyTask``, add your task classes to
it and then call its ``run`` method:

.. code:: python

    # Gevent monkey patching for async tasks
    from gevent import monkey
    monkey.patch_all()

    from pytask import PyTask
    from mytasks import MyTask

    # Create pytask "app"
    task_app = PyTask({'host': 'localhost', 'port': 6379})

    # Add our task to it
    task_app.add_task(MyTask)

    # Run the worker
    task_app.run()
