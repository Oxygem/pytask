# pytask
# File: example/tasks/worker.py
# Desc: a single worker for a pytask "swarm"

# Monkey patch
from gevent import monkey
monkey.patch_all()

# Show logs
import logging
logging.basicConfig(level=logging.DEBUG)

from pytask import PyTask
from pytask.tasks import Monitor, Cleanup

# Create pytask
task_app = PyTask({'host': 'localhost', 'port': 6379})

# Load tasks
from tasks import HelloWorld, Loop
task_app.add_task(HelloWorld)
task_app.add_task(Loop)

# Add the monitor task & pre-start it
task_app.add_task(Monitor)
task_app.add_task(Cleanup)
task_app.start_local_task('pytask/monitor')
task_app.start_local_task('pytask/cleanup')

# Start the worker
task_app.run()
