"""Applications package — the plan 91 Phase 4.2 decomposition of the former
`services/application_service.py` god-module (2216 LOC / ≥7 responsibilities).

External code keeps importing through the `services.application_service`
facade module until the Phase-8 teardown; nothing should import these
submodules directly yet.
"""
