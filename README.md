# pytask

A simple asynchronous Python daemon for IO bound tasks, based on greenlets. Uses Redis or
Redis Cluster to store state; workers are stateless. Included `Monitor` and `Cleanup`
tasks to handle failure of workers.


## Synopsis

```py
from pytask import PyTask, Task

# Create a pytask instance
task_app = PyTask(('localhost', 6379))

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

# Add the task to pytask, and run the worker!
task_app.add_task(MyTask)
task_app.run()
```

To start tasks create an identifier like `TASK_ID`, save the `task` and some JSON `data` to the
task hash and push the `TASK_ID` to the queue:

```sh
redis-cli> HSET task-TASK_ID task test-task
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


## Task Cleanup

When a task ends, it falls into one of the following states:

+ `SUCCESS`
+ `ERROR`
+ `EXCEPTION`

In any of these states, there will also be an `output` key in the tasks hash, containing any
JSON data from the task/exception. The task IDs will also be pushed to the `end-task` queue.

See the `Cleanup` task for automatic cleanup of task data, or the `PyTask.helpers.cleanup_task`
method.


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
