# pytask

A simple Python task daemon for asynchronous IO bound tasks, based on greenlets. Support for distributed/HA setups.


## Synopsis

```py
import redis
from pytask import PyTask, Task

# Create pytask and pass it a Redis instance
task_app = PyTask(redis.StrictRedis())

# A custom task
class MyTask(Task):
    class Config:
        NAME = 'test-task'

    # Configure/prepare the task
    def __init__(self, **task_data):
        self.text = task_data.pop('text', 'hello world')

    # Start the task
    def start(self):
        print self.text

task_app.add_task(MyTask)
task_app.run()
```

To start tasks, set the task name and some JSON task_data to the task has and push the task_id to the queue:

```sh
redis-cli> HSET task-<task_id> task <task_name>
redis-cli> HSET task-<task_id> data <task_data>
redis-cli> LPUSH new-task <task_id>
```

Check out the [full example](./example/).


## Watching & controlling tasks via Redis pub/sub

Tasks can be stopped, started & reloaded via pub/sub. Tasks can also emit events to pub/sub so progress can be watched externally:

```sh
# To control tasks
redis-cli> PUBLISH task-<task_id>-control [stop|start|reload]

# To watch tasks
redis-cli> SUBSCRIBE task-<task_id>

# To watch all tasks:
redis-cli> PSUBSCRIBE task-*
```

Task events are sent as a JSON object, with `event` and `data` keys.


## Ending tasks

When a task completes it's state is set to `ENDED` or `ERROR` depending on the return values. A task can either return one or two values. A single value results in the tasks state being set (`None|True` -> `ENDED` or `False` -> `ERROR`). A second return value means the state is set the same, but the second argument is placed into the task's hash with key `end_data`.

### Cleaning up tasks

By default, PyTask does not cleanup tasks from Redis, instead pushing the `task_id` to the end queue for cleanup by a separate application. You can configure PyTask and each task individually to cleanup upon completion. To make a task cleanup itself on a PyTask instance not configured to do so, simply set the task hash `cleanup` key to `true`.


## Monitoring tasks

pytask includes a task for doing this:

```py
...
from pytask import Monitor
...
task_app.add_task(Monitor)
task_app.pre_start_task('pytask/monitor')
task_app.run()
```


### Exception handling

**TODO: coming soon** - add exception handlers to pytask.


## Redis keys

Defaults below, see `PyTask.__init__` for customization:

+ Task set = `tasks` - a set of all current task_id's
+ Task prefix = `task-` - prefix to all task_id's to get the task hash key
+ New task queue = `new-task` - where to push new task_id's after writing their hash set
+ End task queue = `end-task` - where to read task_id's from tasks that ended (will be state `COMPLETE`, `ERROR` or `EXCEPTION`)


## Distribution/HA

pytask assumes Redis is setup in a highly-available manner (upon disconnect the worker will fail); any client compatible with pyredis will work. Assuming the rest of the pytask instances have access to Redis, and one of them is running a `Monitor` task, the stopped tasks will be requeued.


## Internals

### Task data

Stored has a hash in Redis:

```py
{
    # Required to 'create' task
    'task': 'task_name',
    'data': 'json_data',
    # Created sometimes by pytask
    'end_data': 'json_data',
    # Internally created/used
    'last_update': 0,
    'state': '[RUNNING|STOPPED|COMPLETE|ERROR|EXCEPTION]'
}
```

### Task states

+ `RUNNING` - the task is active, and to be monitored
+ `STOPPED` - the task was intentionally stopped, no monitoring occurs
+ `COMPLETE` - the task ended successfully
+ `ERROR` - the task ended with an error
+ `EXCEPTION` - the task encountered an exception
