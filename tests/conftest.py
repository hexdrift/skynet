from __future__ import annotations

import multiprocessing as mp
from pathlib import Path
import sys
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _reset_global_worker_state() -> None:
    """Ensure module-global worker state is isolated across tests."""
    from core.worker import reset_worker_for_tests

    reset_worker_for_tests()
    yield
    reset_worker_for_tests()


@pytest.fixture(autouse=True)
def _linux_fork_only() -> None:
    """Reliability tests target Linux/OpenShift semantics (`fork` start method)."""
    if "fork" not in mp.get_all_start_methods():
        pytest.skip("Reliability integration tests require multiprocessing 'fork'")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "dspy_jobs_test.db"


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> Path:
    monkeypatch.setenv("JOB_STORE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_DB_PATH", str(db_path))
    monkeypatch.setenv("WORKER_CONCURRENCY", "1")
    monkeypatch.setenv("WORKER_POLL_INTERVAL", "0.05")
    monkeypatch.setenv("CANCEL_POLL_INTERVAL", "0.2")
    monkeypatch.setenv("WORKER_STALE_THRESHOLD", "30")
    monkeypatch.setenv("JOB_RUN_START_METHOD", "fork")
    return db_path


def make_payload(*, username: str = "alice") -> Dict[str, Any]:
    """Create a minimal valid /run payload for integration tests."""
    return {
        "username": username,
        "module_name": "demo_module",
        "module_kwargs": {},
        "signature_code": (
            "import dspy\n"
            "class Sig(dspy.Signature):\n"
            "    question: str = dspy.InputField()\n"
            "    answer: str = dspy.OutputField()\n"
        ),
        "metric_code": (
            "def metric(example, pred, trace=None):\n"
            "    return 1.0\n"
        ),
        "optimizer_name": "demo_optimizer",
        "optimizer_kwargs": {},
        "compile_kwargs": {},
        "dataset": [{"question_col": "q1", "answer_col": "a1"}],
        "column_mapping": {
            "inputs": {"question": "question_col"},
            "outputs": {"answer": "answer_col"},
        },
        "split_fractions": {"train": 1.0, "val": 0.0, "test": 0.0},
        "shuffle": False,
        "seed": 42,
        "model_config": {"name": "dummy-model"},
    }
