"""Self-contained scenarios that exercise the load-test stack.

Each module exposes one ``async def run(config)`` coroutine returning a
:class:`load_tests.lib.metrics.ScenarioResult`. The orchestrator imports the
modules and invokes them in series so each scenario sees a clean baseline.
"""
