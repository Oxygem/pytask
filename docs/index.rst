pytask
======

A simple asynchronous Python daemon for IO bound tasks, based on greenlets. Uses Redis or
Redis Cluster to store state; workers are stateless. Included ``Monitor`` and ``Cleanup``
tasks to handle failure of workers. pytask is designed distributed and :doc:`fault tolerant <fault_tolerance>`.


.. toctree::
    :maxdepth: 1
    :caption: Using pytask

    api
    writing_tasks
    fault_tolerance
