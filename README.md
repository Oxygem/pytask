# pytask

A simple Python task daemon for asynchronous IO bound tasks, based on greenlets. Support for distributed/HA setups.

## Synopsis

```python
import gevent
gevent.monkey.patch_all()
import redis
from pytask import PyTask, Task, Monitor, run_loop

# Create pytask and pass it a Redis instance
task_app = PyTask(redis.StrictRedis())
# Add the in-built Monitor task
task_app.add_task(Monitor)

# A custom task
class MyTask(Task):
    class Config:
        NAME = 'test-task'

    # Start the task
    def __init__(self, task_data):
        self.loop = gevent.spawn(run_loop, self.loop, 10)

    # Do some work
    def loop(self):
        print 'looping...'

    # Stop the task
    def stop(self):
        self.loop.kill()

task_app.add_task(MyTask)
task_app.run()
```


## Distribution/HA

**To monitor for failed tasks** there is an included Monitor task which will do just that `from pytask import Monitor`. Put a task hash in Redis and push the task ID to the queue to start it.

pytask assumes Redis is setup in a highly-available manner; any client compatible with pyredis will work. When the connection to Redis is lost for more than 60 seconds, all tasks are stopped locally. Assuming the rest of the pytask instances have access to Redis, and one of them is running a `Monitor` task, the stopped tasks will be requeued.


## Internals

### Task data

Stored has a hash in Redis:

```py
{
    # Required to 'create' task
    'function': 'task_name',
    'data': 'json_data',
    # Internally created/used
    'last_update': 0,
    'state': '[RUNNING|ENDED|ERROR|STOPPED|WAIT]'
}
```

### Task states

+ `RUNNING` - the task is active, and to be monitoed
+ `ENDED` - the task ended successfully
+ `ERROR` - the task had an error
+ `STOPPED` - the task was intentionally stopped, no monitoring occurs
