"""Notify package — the plan 91 Phase 4.6 decomposition of
`services/notifications.py` into channel transports + event emitters.

External code keeps importing through the `services.notifications` facade
until the Phase-8 teardown; nothing should import these submodules yet.
"""
