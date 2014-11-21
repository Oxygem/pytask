import gevent

from .pytask import Task, run_loop


class Monitor(Task):
    class Config:
        NAME = 'monitor'

    def __init__(self, task_data):
        self.loop = gevent.spawn(run_loop, self.work, 10)

    def stop(self):
        self.loop.stop()

    def work(self):
        print 'loop'
