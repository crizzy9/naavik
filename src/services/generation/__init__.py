"""Generation package — the plan 91 Phase 4.3 decomposition of the former
`services/document_generator.py` god-module (1989 LOC / ≥8 responsibilities).

External code keeps importing through the `services.document_generator`
facade module until the Phase-8 teardown; nothing should import these
submodules directly yet.
"""
