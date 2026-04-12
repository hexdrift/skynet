"""Shared client utilities for Skynet API notebooks.

Provides DSPyServiceClient (HTTP client), JobMonitor (progress polling),
and serialize_source (signature/metric serialization).
"""

import base64
import inspect
import pickle
import textwrap
import time
from typing import Any

import dspy
import requests


class DSPyServiceClient:
    """HTTP client for the Skynet optimization service."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict:
        return requests.get(f"{self.base_url}/health").json()

    def queue(self) -> dict:
        return requests.get(f"{self.base_url}/queue").json()

    def submit(self, payload: dict) -> str:
        resp = requests.post(f"{self.base_url}/run", json=payload)
        resp.raise_for_status()
        return resp.json()["optimization_id"]

    def submit_grid_search(self, payload: dict) -> str:
        resp = requests.post(f"{self.base_url}/grid-search", json=payload)
        resp.raise_for_status()
        return resp.json()["optimization_id"]

    def status(self, optimization_id: str) -> dict:
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}")
        resp.raise_for_status()
        return resp.json()

    def summary(self, optimization_id: str) -> dict:
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/summary")
        resp.raise_for_status()
        return resp.json()

    def logs(self, optimization_id: str, level: str | None = None, limit: int | None = None) -> list:
        params = {}
        if level:
            params["level"] = level
        if limit:
            params["limit"] = limit
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/logs", params=params)
        resp.raise_for_status()
        return resp.json()

    def artifact(self, optimization_id: str) -> dict:
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/artifact")
        resp.raise_for_status()
        return resp.json()

    def grid_result(self, optimization_id: str) -> dict:
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/grid-result")
        resp.raise_for_status()
        return resp.json()

    def dataset(self, optimization_id: str) -> dict:
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/dataset")
        resp.raise_for_status()
        return resp.json()

    def test_results(self, optimization_id: str) -> dict:
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/test-results")
        resp.raise_for_status()
        return resp.json()

    def cancel(self, optimization_id: str) -> dict:
        resp = requests.post(f"{self.base_url}/optimizations/{optimization_id}/cancel")
        resp.raise_for_status()
        return resp.json()

    def delete(self, optimization_id: str) -> None:
        resp = requests.delete(f"{self.base_url}/optimizations/{optimization_id}")
        resp.raise_for_status()

    def validate_code(self, payload: dict) -> dict:
        resp = requests.post(f"{self.base_url}/validate-code", json=payload)
        resp.raise_for_status()
        return resp.json()

    def serve_info(self, optimization_id: str) -> dict:
        resp = requests.get(f"{self.base_url}/serve/{optimization_id}/info")
        resp.raise_for_status()
        return resp.json()

    def serve(self, optimization_id: str, inputs: dict) -> dict:
        resp = requests.post(f"{self.base_url}/serve/{optimization_id}", json=inputs)
        resp.raise_for_status()
        return resp.json()

    def load_program(self, optimization_id: str) -> dspy.Module:
        art = self.artifact(optimization_id)
        pickle_b64 = art["program_artifact"]["program_pickle_base64"]
        return pickle.loads(base64.b64decode(pickle_b64))

    def list_optimizations(self, **params) -> dict:
        resp = requests.get(f"{self.base_url}/optimizations", params=params)
        resp.raise_for_status()
        return resp.json()

    def models(self) -> list:
        return requests.get(f"{self.base_url}/models").json()


class JobMonitor:
    """Poll an optimization job and print formatted progress."""

    def __init__(self, client: DSPyServiceClient, optimization_id: str):
        self.client = client
        self.optimization_id = optimization_id
        self._printed_events = 0
        self._printed_logs = 0

    def poll(self, interval: int = 5, timeout: int | None = None) -> dict:
        start = time.time()
        while True:
            data = self.client.status(self.optimization_id)
            elapsed = time.time() - start
            self._print_update(data, elapsed)
            if data["status"] in {"success", "failed", "cancelled"}:
                return data
            if timeout and elapsed > timeout:
                raise TimeoutError(f"Job {self.optimization_id} timed out after {timeout}s")
            time.sleep(interval)

    def _print_update(self, data: dict, elapsed: float) -> None:
        ts = time.strftime("%H:%M:%S")
        metrics = data.get("latest_metrics") or {}
        parts = [f"[{ts}] {data['status'].upper():<12} | {int(elapsed)}s"]
        if "tqdm_percent" in metrics:
            parts.append(f"{metrics['tqdm_percent']:.0f}%")
        if "baseline_test_metric" in metrics:
            parts.append(f"baseline={metrics['baseline_test_metric']:.2f}")
        if "optimized_test_metric" in metrics:
            parts.append(f"optimized={metrics['optimized_test_metric']:.2f}")
        print(" | ".join(parts))

        events = data.get("progress_events", [])
        for ev in events[self._printed_events :]:
            m = ev.get("metrics", {})
            if "tqdm_desc" in m:
                print(f"    {m['tqdm_desc']}: {m.get('tqdm_n', '?')}/{m.get('tqdm_total', '?')}")
        self._printed_events = len(events)

        logs = data.get("logs", [])
        for log in logs[self._printed_logs :]:
            level = log.get("level", "INFO")
            if level in {"INFO", "WARNING", "ERROR"}:
                print(f"    [{level}] {log.get('message', '')[:100]}")
        self._printed_logs = len(logs)


def serialize_source(obj: Any) -> str:
    """Serialize a DSPy Signature class or function to source code string."""
    if isinstance(obj, type) and issubclass(obj, dspy.Signature):
        doc = obj.__doc__ or ""
        lines = [
            f"class {obj.__name__}(dspy.Signature):",
            f'    """{doc}"""',
        ]
        for name, field in obj.model_fields.items():
            extra = field.json_schema_extra or {}
            ftype = "InputField" if extra.get("__dspy_field_type") == "input" else "OutputField"
            desc = extra.get("desc", "")
            lines.append(f'    {name}: str = dspy.{ftype}(desc="{desc}")')
        return "\n".join(lines)

    if hasattr(obj, "__source_code__"):
        return obj.__source_code__

    try:
        return textwrap.dedent(inspect.getsource(obj)).strip()
    except (OSError, TypeError) as e:
        raise RuntimeError(
            f"Cannot extract source from {obj}. Define metric as a string: METRIC_CODE = '''def metric(...): ...'''"
        ) from e
