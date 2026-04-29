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

# All HTTP calls to the service share the same generous timeout: long enough
# to absorb a slow grid-search detail fetch, short enough to fail fast if the
# server is unreachable rather than letting a notebook hang forever.
_REQUEST_TIMEOUT = 30


class DSPyServiceClient:
    """HTTP client for the Skynet optimization service."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize the client.

        Args:
            base_url: Base URL of the Skynet service. Trailing slash is stripped.
        """
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict:
        """Fetch the service health status.

        Returns:
            The ``GET /health`` response payload.
        """
        resp = requests.get(f"{self.base_url}/health", timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def queue(self) -> dict:
        """Fetch the worker queue state.

        Returns:
            The ``GET /queue`` response payload (running/pending counts, workers).
        """
        resp = requests.get(f"{self.base_url}/queue", timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def submit(self, payload: dict) -> str:
        """Submit a single optimization job.

        Args:
            payload: Full ``POST /run`` request body (signature, metric, dataset, etc.).

        Returns:
            The newly created ``optimization_id``.
        """
        resp = requests.post(f"{self.base_url}/run", json=payload)
        resp.raise_for_status()
        return resp.json()["optimization_id"]

    def submit_grid_search(self, payload: dict) -> str:
        """Submit a grid-search optimization job.

        Args:
            payload: Full ``POST /grid-search`` request body.

        Returns:
            The newly created ``optimization_id``.
        """
        resp = requests.post(f"{self.base_url}/grid-search", json=payload)
        resp.raise_for_status()
        return resp.json()["optimization_id"]

    def status(self, optimization_id: str) -> dict:
        """Fetch the full detail record for an optimization.

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The ``GET /optimizations/{id}`` response payload.
        """
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}")
        resp.raise_for_status()
        return resp.json()

    def summary(self, optimization_id: str) -> dict:
        """Fetch the compact summary card for an optimization.

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The ``GET /optimizations/{id}/summary`` response payload.
        """
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/summary")
        resp.raise_for_status()
        return resp.json()

    def logs(self, optimization_id: str, level: str | None = None, limit: int | None = None) -> list:
        """Fetch log entries emitted during an optimization.

        Args:
            optimization_id: The optimization job identifier.
            level: Optional log-level filter (e.g. ``"INFO"``, ``"ERROR"``).
            limit: Optional cap on the number of entries returned.

        Returns:
            A list of log-entry dicts from ``GET /optimizations/{id}/logs``.
        """
        params: dict[str, str | int] = {}
        if level:
            params["level"] = level
        if limit is not None:
            params["limit"] = limit
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/logs", params=params)
        resp.raise_for_status()
        return resp.json()

    def artifact(self, optimization_id: str) -> dict:
        """Fetch the full program artifact (including pickled program).

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The ``GET /optimizations/{id}/artifact`` response payload.
        """
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/artifact")
        resp.raise_for_status()
        return resp.json()

    def grid_result(self, optimization_id: str) -> dict:
        """Fetch the per-cell grid-search results.

        Args:
            optimization_id: The grid-search job identifier.

        Returns:
            The ``GET /optimizations/{id}/grid-result`` response payload.
        """
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/grid-result")
        resp.raise_for_status()
        return resp.json()

    def dataset(self, optimization_id: str) -> dict:
        """Fetch the dataset stored for an optimization.

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The ``GET /optimizations/{id}/dataset`` response payload.
        """
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/dataset")
        resp.raise_for_status()
        return resp.json()

    def test_results(self, optimization_id: str) -> dict:
        """Fetch the baseline/optimized test-set predictions.

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The ``GET /optimizations/{id}/test-results`` response payload.
        """
        resp = requests.get(f"{self.base_url}/optimizations/{optimization_id}/test-results")
        resp.raise_for_status()
        return resp.json()

    def cancel(self, optimization_id: str) -> dict:
        """Request cancellation of a running optimization.

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The ``POST /optimizations/{id}/cancel`` response payload.
        """
        resp = requests.post(f"{self.base_url}/optimizations/{optimization_id}/cancel")
        resp.raise_for_status()
        return resp.json()

    def delete(self, optimization_id: str) -> dict:
        """Delete a terminal optimization record.

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The ``DELETE /optimizations/{id}`` acknowledgement payload.
        """
        resp = requests.delete(f"{self.base_url}/optimizations/{optimization_id}")
        resp.raise_for_status()
        return resp.json()

    def validate_code(self, payload: dict) -> dict:
        """Validate a signature/metric code snippet without running it.

        Args:
            payload: ``POST /validate-code`` request body (code + target type).

        Returns:
            The validation result payload.
        """
        resp = requests.post(f"{self.base_url}/validate-code", json=payload)
        resp.raise_for_status()
        return resp.json()

    def serve_info(self, optimization_id: str) -> dict:
        """Fetch the serving metadata for an optimized program.

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The ``GET /serve/{id}/info`` response payload.
        """
        resp = requests.get(f"{self.base_url}/serve/{optimization_id}/info")
        resp.raise_for_status()
        return resp.json()

    def serve(self, optimization_id: str, inputs: dict) -> dict:
        """Run inference against a served optimized program.

        Args:
            optimization_id: The optimization job identifier.
            inputs: Input-field values matching the program's signature.

        Returns:
            The ``POST /serve/{id}`` response payload with predictions.
        """
        resp = requests.post(f"{self.base_url}/serve/{optimization_id}", json=inputs)
        resp.raise_for_status()
        return resp.json()

    def load_program(self, optimization_id: str) -> dspy.Module:
        """Download and unpickle the optimized program.

        Args:
            optimization_id: The optimization job identifier.

        Returns:
            The live ``dspy.Module`` instance ready for inference.

        Security:
            This unpickles bytes returned by the configured Skynet service.
            ``pickle.loads`` runs arbitrary code during deserialization, so
            only call this against a service whose artifact store you trust.
            Treat a shared/multi-tenant Skynet instance as untrusted.
        """
        art = self.artifact(optimization_id)
        pickle_b64 = art["program_artifact"]["program_pickle_base64"]
        return pickle.loads(base64.b64decode(pickle_b64))

    def list_optimizations(self, **params) -> dict:
        """List optimization jobs matching the given filters.

        Args:
            **params: Query parameters forwarded to ``GET /optimizations``
                (e.g. ``username``, ``status``, ``limit``, ``offset``).

        Returns:
            The paginated list response (``items``, ``total``, etc.).
        """
        resp = requests.get(f"{self.base_url}/optimizations", params=params)
        resp.raise_for_status()
        return resp.json()

    def models(self) -> list:
        """Fetch the catalog of models available to the service.

        Returns:
            The ``GET /models`` response payload.
        """
        resp = requests.get(f"{self.base_url}/models", timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()


class JobMonitor:
    """Poll an optimization job and print formatted progress."""

    def __init__(self, client: DSPyServiceClient, optimization_id: str):
        """Initialize the monitor.

        Args:
            client: Skynet client used to fetch job status.
            optimization_id: The optimization job identifier to poll.
        """
        self.client = client
        self.optimization_id = optimization_id
        self._printed_events = 0
        self._printed_logs = 0

    def poll(self, interval: int = 5, timeout: int | None = None) -> dict:
        """Poll the job until it reaches a terminal status or times out.

        Args:
            interval: Seconds to wait between status requests.
            timeout: Optional overall timeout in seconds; ``None`` to poll forever.

        Returns:
            The final job detail dict once status is ``success``/``failed``/``cancelled``.

        Raises:
            TimeoutError: If *timeout* is set and elapsed time exceeds it.
        """
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
        """Print a single progress line plus any new events/logs.

        Advances ``self._printed_events`` and ``self._printed_logs`` so each
        subsequent call only emits the unseen tail — calling twice on the same
        snapshot is therefore safe and produces no duplicate output.

        Args:
            data: The latest job detail dict from ``client.status``.
            elapsed: Seconds since polling started, used in the status line.
        """
        ts = time.strftime("%H:%M:%S")
        metrics = data.get("latest_metrics") or {}
        parts = [f"[{ts}] {data.get('status', '?').upper():<12} | {int(elapsed)}s"]
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
            print(f"    [{level}] {log.get('message', '')[:100]}")
        self._printed_logs = len(logs)


def serialize_source(obj: Any) -> str:
    """Serialize a DSPy Signature class or function to source code string.

    Args:
        obj: A ``dspy.Signature`` subclass, a callable with ``__source_code__``,
            or any object accepted by ``inspect.getsource``.

    Returns:
        The source code as a string, suitable for sending to the service.

    Raises:
        RuntimeError: If source cannot be extracted (e.g. function defined
            interactively without a file backing it).
    """
    if isinstance(obj, type) and issubclass(obj, dspy.Signature):
        doc = obj.__doc__ or ""
        # ``repr()`` produces a quoted, escaped Python string literal — safe
        # for docstrings/descs that contain quotes or backslashes, which a
        # naive f-string-with-double-quotes would corrupt.
        lines = [
            f"class {obj.__name__}(dspy.Signature):",
            f"    {doc!r}",
        ]
        for name, field in obj.model_fields.items():
            extra = field.json_schema_extra or {}
            ftype = "InputField" if extra.get("__dspy_field_type") == "input" else "OutputField"
            desc = extra.get("desc", "")
            type_name = inspect.formatannotation(field.annotation) if field.annotation else "str"
            lines.append(f"    {name}: {type_name} = dspy.{ftype}(desc={desc!r})")
        return "\n".join(lines)

    if hasattr(obj, "__source_code__"):
        return obj.__source_code__

    try:
        return textwrap.dedent(inspect.getsource(obj)).strip()
    except (OSError, TypeError) as e:
        raise RuntimeError(
            f"Cannot extract source from {obj}. Define metric as a string: METRIC_CODE = '''def metric(...): ...'''"
        ) from e
