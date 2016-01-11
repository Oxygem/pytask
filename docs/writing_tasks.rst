Writing Tasks
=============

A simple pytask might look like:

.. code:: python

    # Define a task
    class MyTask(Task):
        # Used to create tasks of this type
        NAME = 'test-task'

        # Configure/prepare the task
        def __init__(self, **task_data):
            self.text = task_data.get('text', 'hello world')

        # Start the task
        def start(self):
            print self.text


Data & Init
-----------


Start & Stop
------------


Emitting Events
---------------


Handling Errors
---------------
