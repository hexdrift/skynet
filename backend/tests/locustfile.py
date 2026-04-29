"""Locust load test for Skynet API.

User persona: a data-scientist who periodically submits optimization jobs,
monitors their progress, and queries the job list between submissions.
The task weights reflect realistic usage: reads are far more frequent than writes.

Task tag summary:
    read  — GET-only, no side effects (health, queue, jobs listing, 404 probe)
    write — mutating requests (job submit + cancel, invalid submit)

Run (interactive):
    cd backend && ../.venv/bin/locust -f tests/locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 for the Locust dashboard.

Headless mode (CI):
    locust -f tests/locustfile.py --host=http://localhost:8000 \\
        --headless -u 50 -r 10 --run-time 60s

Expected shape at 50 users, 10 rps spawn rate (local single-worker dev server):
    - /health p99 < 200 ms
    - /optimizations    p99 < 1 s
    - POST /run p99 < 3 s (accepted synchronously, LLM runs async)
"""

import os

from locust import HttpUser, between, tag, task

LOAD_TEST_MODEL = os.getenv("LOAD_TEST_MODEL", "openai/gpt-5.4-nano")


class SkynetAPIUser(HttpUser):
    """Simulates a data-scientist using the Skynet API.

    Read tasks run ~28x more often than write tasks. The single "submit and
    track" write task cancels the job immediately to avoid burning LLM credits
    during load testing.
    """

    wait_time = between(0.5, 2.0)

    @tag("read")
    @task(10)
    def health_check(self):
        """Hit the ``/health`` endpoint, the cheapest read path."""
        self.client.get("/health")

    @tag("read")
    @task(5)
    def queue_status(self):
        """Fetch the queue snapshot used by the dashboard."""
        self.client.get("/queue")

    @tag("read")
    @task(8)
    def list_jobs(self):
        """Page through recent optimizations (default sort, limit 10)."""
        self.client.get("/optimizations?limit=10")

    @tag("read")
    @task(3)
    def list_jobs_filtered_by_status(self):
        """List successful jobs, exercising the indexed status filter."""
        self.client.get("/optimizations?status=success&limit=5")

    @tag("read")
    @task(2)
    def list_jobs_by_user(self):
        """List jobs for the synthetic ``locust-test`` user."""
        self.client.get("/optimizations?username=locust-test&limit=10")

    @tag("read")
    @task(1)
    def probe_nonexistent_job(self):
        """Hit a known-missing id to exercise the 404 fast path under load."""
        with self.client.get("/optimizations/nonexistent-locust-id", catch_response=True) as r:
            if r.status_code == 404:
                r.success()

    @tag("write")
    @task(1)
    def submit_job_then_cancel(self):
        """Submit a real job and cancel it immediately to avoid burning API credits."""
        payload = {
            "username": "locust-test",
            "module_name": "predict",
            "signature_code": (
                "import dspy\n"
                "class S(dspy.Signature):\n"
                "    q: str = dspy.InputField()\n"
                "    a: str = dspy.OutputField()\n"
            ),
            "metric_code": "def metric(e, p, t=None): return 1.0\n",
            "optimizer_name": "gepa",
            "dataset": [{"q": "test", "a": "test"}],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "model_config": {"name": LOAD_TEST_MODEL},
        }
        with self.client.post("/run", json=payload, catch_response=True) as r:
            if r.status_code == 201:
                r.success()
                job_id = r.json()["optimization_id"]
                self.client.get(f"/optimizations/{job_id}/summary")
                # Cancel immediately — avoids burning API credits during load runs
                self.client.post(f"/optimizations/{job_id}/cancel")
            else:
                r.failure(f"Submit failed: {r.status_code} {r.text[:200]}")

    @tag("write")
    @task(2)
    def submit_invalid_payload(self):
        """Send a malformed payload to exercise the 422 validation fast path."""
        with self.client.post("/run", json={"username": "bad"}, catch_response=True) as r:
            if r.status_code == 422:
                r.success()
            else:
                r.failure(f"Expected 422, got {r.status_code}")
