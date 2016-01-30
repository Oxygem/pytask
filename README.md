# pytask [![PyPI version](https://badge.fury.io/py/pytask.svg)](https://pypi.python.org/pypi/pytask)

A simple asynchronous Python daemon for IO bound tasks, based on greenlets. Uses Redis or
Redis Cluster to store state; workers are stateless. Included `Monitor` and `Cleanup`
tasks to handle failure of workers.

+ [Documentation](https://pytask.readthedocs.org)


## Synopsis

```py
from pytask import PyTask, Task

# Create a pytask instance
task_app = PyTask({'host': 'localhost', 'port': 6379})

# Define a task
class MyTask(Task):
    # Used to create tasks of this type
    NAME = 'my-task'

    # Configure/prepare the task
    def __init__(self, text='hello world'):
        self.text = text

    # Start the task
    def start(self):
        print self.text

# Add the task to pytask, and run the worker!
task_app.add_task(MyTask)
task_app.run()
```

To start tasks create an identifier like `TASK_ID`, save the `task` and some JSON `data` to the
task hash and push the `TASK_ID` to the queue:

```sh
redis-cli> HSET task-TASK_ID task my-task
redis-cli> HSET task-TASK_ID data '{"text": "Not hello world"}'
redis-cli> LPUSH new-task TASK_ID
```

Check out the [full example](./example/).


## Interact with tasks via Redis pub/sub

Tasks emit events which can be subscribed to with Redis, see `Task.emit` to generate your own
events. Tasks can also be stopped & reloaded by publishing to Redis.

```sh
# To watch tasks
redis-cli> SUBSCRIBE task-<task_id>

# To watch all tasks:
redis-cli> PSUBSCRIBE task-*

# To control tasks
redis-cli> PUBLISH task-<task_id>-control [stop|reload]
```

Task events are sent as a JSON object, with `event` and `data` keys.


## Monitor/Cleanup & Clustering

pytask workers are stateless, meaning they can be "clustered" alongside a Redis cluster. Two
tasks are included which ensure failed tasks and restarted and cleaned up. Normally every worker
starts these tasks locally (all workers effectively monitor each others & own tasks):

```py
from pytask import Monitor, Cleanup

task_app.add_tasks(Monitor, Cleanup)

task_app.start_local_task('pytask/monitor')
task_app.start_local_task('pytask/cleanup')

task_app.run()
```

For more information see [clustering pytask](https://pytask.readthedocs.org/clustering_pytask.html).
