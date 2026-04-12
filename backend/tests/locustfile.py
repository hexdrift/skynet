"""Locust load test for Skynet API.

Run:
    cd backend && ../.venv/bin/locust -f tests/locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 for the dashboard.

Headless mode (CI):
    locust -f tests/locustfile.py --host=http://localhost:8000 \
        --headless -u 50 -r 10 --run-time 60s
"""

from locust import HttpUser, between, tag, task


class SkynetAPIUser(HttpUser):
    """Simulates a typical Skynet API user."""

    wait_time = between(0.5, 2.0)

    @tag("read")
    @task(10)
    def health_check(self):
        """High-frequency health check."""
        self.client.get("/health")

    @tag("read")
    @task(5)
    def queue_status(self):
        """Check queue status."""
        self.client.get("/queue")

    @tag("read")
    @task(8)
    def list_jobs(self):
        """List jobs with various filters."""
        self.client.get("/jobs?limit=10")

    @tag("read")
    @task(3)
    def list_jobs_filtered(self):
        """List jobs with status filter."""
        self.client.get("/jobs?status=success&limit=5")

    @tag("read")
    @task(2)
    def list_jobs_by_user(self):
        """List jobs filtered by username."""
        self.client.get("/jobs?username=locust-test&limit=10")

    @tag("read")
    @task(1)
    def get_nonexistent_job(self):
        """404 lookup — tests error path performance."""
        with self.client.get("/jobs/nonexistent-locust-id", catch_response=True) as r:
            if r.status_code == 404:
                r.success()

    @tag("write")
    @task(1)
    def submit_and_track_job(self):
        """Submit a real job, poll once, then clean up."""
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
            "optimizer_name": "miprov2",
            "dataset": [{"q": "test", "a": "test"}],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "model_config": {"name": "gpt-4o-mini"},
        }
        with self.client.post("/run", json=payload, catch_response=True) as r:
            if r.status_code == 201:
                r.success()
                job_id = r.json()["job_id"]
                self.client.get(f"/jobs/{job_id}/summary")
                # Cancel to avoid burning API credits
                self.client.post(f"/jobs/{job_id}/cancel")
            else:
                r.failure(f"Submit failed: {r.status_code}")

    @tag("write")
    @task(2)
    def submit_invalid(self):
        """Submit invalid payload — tests validation path."""
        with self.client.post("/run", json={"username": "bad"}, catch_response=True) as r:
            if r.status_code == 422:
                r.success()
