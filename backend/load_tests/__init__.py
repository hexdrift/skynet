"""Skynet end-to-end load-test suite.

Layout:
  - ``mock_lm/``  OpenAI-compatible mock LM container (no real provider calls).
  - ``lib/``      Reusable helpers: auth, payloads, metrics, runner, db, reporter.
  - ``scenarios/`` One module per load-test scenario (submission burst, full
    lifecycle, dashboard read, failure injection).
  - ``run_all.py`` Orchestrator: boot compose stack, run scenarios, emit reports.
  - ``docker-compose.loadtest.yml`` Multi-pod stack (postgres + pgbouncer +
    mock-lm + 3 api replicas behind an nginx LB).

Drive everything with ``python -m load_tests.run_all`` from ``backend/``.
"""
