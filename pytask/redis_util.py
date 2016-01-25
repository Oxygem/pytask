# pytask
# File: pytask/redis_util.py
# Desc: pytask Redis normalisation

from redis import StrictRedis
from redis.exceptions import ConnectionError

# We always have Redis
redis_clients = [StrictRedis]
redis_errors = [ConnectionError]

try:
    # Get optional cluster
    from rediscluster import StrictRedisCluster
    from rediscluster.exceptions import ClusterDownException

    redis_clients.append(StrictRedisCluster)
    redis_errors.append(ClusterDownException)

except ImportError:
    StrictRedisCluster = None

# For isinstance and exception capturing
redis_clients = tuple(redis_clients)
redis_errors = tuple(redis_errors)


def make_redis(args):
    '''
    Makes a ``RedisCluster`` or ``Redis`` instance (when list/dict, not instance, is
    passed to ``PyTask.__init__``.
    '''

    if StrictRedisCluster:
        return StrictRedisCluster(args, decode_responses=True)
    else:
        return StrictRedis(**args)
