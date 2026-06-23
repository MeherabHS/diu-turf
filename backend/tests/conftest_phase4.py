"""Minimal conftest for Phase 4 unit tests.

Phase 4 tests are pure unit tests — no MongoDB, no PostgreSQL, no running server.
Use: pytest tests/test_phase4_auth.py --override-ini="python_files=test_phase4*.py"
Or:  pytest tests/test_phase4_auth.py -p no:conftest  (skip main conftest)
"""
