# pytask
# File: example/tasks/worker.py
# Desc: a single worker for a pytask "swarm"

import gevent
gevent.monkey.patch_all()
import redis
from pytask import PyTask, Monitor

# Create pytask and pass it a Redis instance
task_app = PyTask(redis.StrictRedis())

# Load tasks
from .tasks import HelloWorld, Loop
task_app.add_task(HelloWorld)
task_app.add_task(Loop)

# Add the monitor task & pre-start it
task_app.add_task(Monitor)
task_app.pre_start_task('pytask/monitor')

# Start the worker
task_app.run()
