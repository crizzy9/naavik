"""Resolution package — the plan 91 Phase 4.5 decomposition of
`services/apply_site_resolver.py` + `services/linkedin_resolver.py`.

External code keeps importing through the `services.apply_site_resolver` /
`services.linkedin_resolver` facades until the Phase-8 teardown; nothing
should import these submodules directly yet.
"""
