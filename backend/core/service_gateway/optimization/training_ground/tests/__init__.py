"""Test package for the training_ground harness.

Tests in this package are pure-Python — no live MCP, no DB, no LM. They
exist to lock the behavioral contracts that the Codex review surfaced
(see ``training_ground_SPEC.md`` §5, §6, §8, §11) so regressions trip
in CI rather than at the next optimize run.
"""
