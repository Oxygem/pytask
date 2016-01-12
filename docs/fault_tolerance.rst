Fault Tolerance
===============

pytask leans on Redis to handle its state - this means pytask workers are stateless, and
can be scaled horizontally. Combined with a Redis cluster you have a fullly distributed and
somewhat fault tolerant task system. For example:

+ 3x servers
+ Each has one instance of Redis clustered
+ Each runs 4 workers


Data Model
----------

+ New task IDs and ended task IDs are pushed to two Redis list queues (LPUSH/RPOP)
+ "Active" tasks are stored in a set
+ A task is represented by a Redis hash (it's key is the task ID w/prefix):

.. code:: python

    {
        'task': 'task_name', # the NAME attribute of the task class
        'data': 'json_data', # JSON data passed to the task
        'last_update': 0, # Internal update counter, used to requeue failed worker tasks
        'state': '[RUNNING|STOPPED|SUCCESS|ERROR|EXCEPTION]', # tasks current state

        # Present on ended tasks:
        'output': 'json_data' # output JSON data or exception data
    }

At any one time, all task_ids the system is aware of are stored in the task set, new and
end queues. Task hashes without their keys in one of these lists would be orphaned.


Task States
-----------

Before task starts:
    When the task is waiting to be picked by a worker - it's ID should be in the new task
    queue. Represented by no value or ``WAIT``.

``RUNNING``:
    These tasks are monitored and "locked" to their worker by update time. Monitor tasks
    will requeue these tasks when their update time is over a configurable threshold.

``STOPPED``:
    These tasks were intentionally stopped before they could complete. They can be
    restarted (possibly any worker) by pushing the task ID onto the new queue.

``SUCCESS``, ``ERROR`` & ``EXCEPTION``:
    These tasks have finished, and should have an associated ``output`` in their hash set.


Worker Failure
--------------

Expected/SIGINT:
    The worker will stop and requeue any running tasks, and set their state to ``WAIT``.

Unexpected:
    The worker will stop updating ``update_time`` on its tasks. Any monitor tasks will
    pick this up (depending on configuration) and requeue the failed workers tasks.


Redis Failure
-------------

Partitons:
    When workers can't reach Redis, they stop all their tasks. So long as there is still
    a Redis cluster and some worker instances reaching it, these tasks will be requeued.

Complete failure:
    In the case where Redis is offline for all workers, the task cluster will essentialy
    stop. A usable Redis cluster is *always* required.
