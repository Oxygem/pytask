# v1.1 (WIP)

+ [Breaking] Refactored API, documentation, future versions to follow semver
+ Implemented `Monitor` and `Cleanup` tasks
+ Add optional `provide_context` staticmethod to `Task`
+ Local tasks properly supported, and added/removed/cleaned from Redis
+ Full support for Redis & Redis cluster

# v1.0.2

+ Fixed not unsubscribing to task pubsub messages
+ Better cleanup of `pre_start` tasks
+ Added changelog
