# pytask

A simple Python task daemon for IO bound tasks, using greenlets. Support for distributed/HA setups.

## Synopsis

```python
import redis
from pytask import PyTask, Task

task_app = PyTask(redis.StrictRedis())

class TestTask(Task):
    class Config:
        NAME = 'test-task'

    def __init__(self, task_data):
        print 'running...'

    def stop(self):
        print 'stopping...'

task_app.add_task(TestTask)
task_app.run()
```


## Distribution/HA

**To monitor for failed tasks** there is an included Monitor task which will do just that `from pytask import Monitor`. Put a task hash in Redis and push the task ID to the queue to start it.

pytask assumes Redis is setup in a highly-available manner; any client compatible with pyredis will work. When the connection to Redis is lost for more than 60 seconds, all tasks are stopped locally. Assuming the rest of the pytask instances have access to Redis, and one of them is running a `Monitor` task, the stopped tasks will be requeued.


## Internals

### Task data

Stored has a hash in Redis:

```js
{
    // Required to 'create' task
    "function": "task_name",
    "data": "json_data",
    // Internally created/used
    "last_update": 0,
    "state": "[RUNNING|ENDED|ERROR|STOPPED|WAIT]"
}
```

### Task states

+ `RUNNING` - the task is active, and to be monitoed
+ `ENDED` - the task ended successfully
+ `ERROR` - the task had an error
+ `STOPPED` - the task was intentionally stopped, no monitoring occurs
