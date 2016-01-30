pytask
======

A simple asynchronous Python daemon for IO bound tasks, based on greenlets. Uses Redis or
Redis Cluster to store state; workers are stateless. Included ``Monitor`` and ``Cleanup``
tasks to handle failure of workers. pytask is designed distributed and :doc:`fault tolerant <fault_tolerance>`.


.. toctree::
    :maxdepth: 1
    :caption: Using pytask

    starting_workers
    writing_tasks
    api


.. toctree::
    :maxdepth: 1
    :caption: pytask Clusters

    clustering_pytask
    fault_tolerance


.. toctree::
    :hidden:
    :caption: Elsewhere

    pytask on GitHub <http://github.com/Oxygem/pytask>
