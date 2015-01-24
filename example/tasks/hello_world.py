# pytask
# File: example/tasks/hello_world.py
# Desc: a simple hello world printing task

from .pytask import Task


class HelloWorld(Task):
    NAME = 'hello_world'

    def start(self):
        print 'HELLO {}'.format(self.task_data.get('hello', 'WORLD'))
