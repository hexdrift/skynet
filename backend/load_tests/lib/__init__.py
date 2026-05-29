"""Shared utilities for Skynet load-test scenarios.

Submodules:
    auth: Mint signed bearer tokens accepted by ``get_authenticated_user``.
    metrics: Latency histograms, throughput counters, percentile helpers.
    payloads: Canonical run + grid-search request builders pointed at the mock LM.
    runner: Async request driver returning a ``ScenarioResult``.
    db: Direct Postgres inspector for invariants the API does not expose.
    reporter: Console + JSON renderers for ``ScenarioResult`` bundles.
"""
