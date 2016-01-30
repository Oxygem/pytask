Clustering pytask
=================

pytask leans on Redis to handle its state - this means pytask workers are stateless, and
can be scaled horizontally. Combined with a Redis cluster you have a fullly distributed and
:doc:`somewhat fault tolerant <./fault_tolerance>` task system. For example:

+ 3x servers
+ Each has one instance of Redis clustered
+ Each runs 4 workers
