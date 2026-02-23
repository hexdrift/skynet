"""End-to-end UX journey test using a realistic customer-support-classification payload.

Exercises every API endpoint and collects UX pain points.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.models import RunResponse, SplitCounts
from core.worker import reset_worker_for_tests


# ---------------------------------------------------------------------------
# Realistic mock service that emulates tqdm progress from BootstrapFewShot
# ---------------------------------------------------------------------------
class RealisticClassificationService:
    """Mock service that simulates a ticket-classification optimization."""

    def validate_payload(self, payload) -> None:
        time.sleep(0.05)

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        logger = logging.getLogger("dspy")
        logger.info("Starting ticket classification optimization job=%s", artifact_id)

        # Emit dataset_splits_ready
        if progress_callback:
            progress_callback("dataset_splits_ready", {
                "train": 3, "val": 1, "test": 1,
            })

        time.sleep(0.05)

        # Emit baseline evaluation
        if progress_callback:
            progress_callback("baseline_evaluated", {"baseline_test_metric": 0.6})

        # Simulate tqdm optimizer progress: 3 rounds of bootstrap
        if progress_callback:
            for step, (n, elapsed) in enumerate([
                (10, 1.0), (50, 5.0), (80, 8.0), (100, 10.0)
            ]):
                progress_callback("optimizer_progress", {
                    "tqdm_total": 100,
                    "tqdm_n": n,
                    "tqdm_elapsed": elapsed,
                    "tqdm_rate": n / elapsed if elapsed > 0 else 0,
                    "tqdm_remaining": (100 - n) / (n / elapsed) if n > 0 and elapsed > 0 else None,
                    "tqdm_percent": float(n),
                    "tqdm_desc": "GEPA Optimization",
                })
                time.sleep(0.05)

        # Emit optimized evaluation
        if progress_callback:
            progress_callback("optimized_evaluated", {"optimized_test_metric": 0.9})

        logger.info("Optimization complete for job=%s", artifact_id)

        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=3, val=1, test=1),
            baseline_test_metric=0.6,
            optimized_test_metric=0.9,
            metric_improvement=0.3,
            optimization_metadata={
                "optimizer": payload.optimizer_name,
                "optimizer_kwargs": {"max_bootstrapped_demos": 2},
                "compile_kwargs": {},
                "module_kwargs": {},
                "model_identifier": "openai/gpt-4o-mini",
            },
            details={
                "train": 3, "val": 1, "test": 1,
                "baseline_test_metric": 0.6,
                "optimized_test_metric": 0.9,
            },
            runtime_seconds=0.5,
        )


# ---------------------------------------------------------------------------
# Realistic payload: customer support ticket classification
# ---------------------------------------------------------------------------
REALISTIC_PAYLOAD: Dict[str, Any] = {
    "username": "support_team",
    "module_name": "cot",
    "module_kwargs": {},
    "signature_code": (
        "import dspy\n\n"
        "class ClassifyTicket(dspy.Signature):\n"
        '    """Classify a customer support ticket into the correct department."""\n'
        "    ticket_text: str = dspy.InputField(desc='The customer support ticket message')\n"
        "    category: str = dspy.OutputField(desc='One of: billing, technical, account, shipping')\n"
    ),
    "metric_code": (
        "def metric(example, pred, trace=None):\n"
        "    return float(example.category.strip().lower() == pred.category.strip().lower())\n"
    ),
    "optimizer_name": "dspy.BootstrapFewShot",
    "optimizer_kwargs": {
        "max_bootstrapped_demos": 2,
        "max_labeled_demos": 2,
        "max_rounds": 1,
    },
    "compile_kwargs": {},
    "dataset": [
        {"ticket": "I was charged twice for order #4821. Please refund.", "label": "billing"},
        {"ticket": "App crashes when uploading profile picture on iOS 17.", "label": "technical"},
        {"ticket": "Need to update email on my account, old one was compromised.", "label": "account"},
        {"ticket": "Package shows delivered but never received. TRK-99281.", "label": "shipping"},
        {"ticket": "500 error when exporting data from dashboard.", "label": "technical"},
    ],
    "column_mapping": {
        "inputs": {"ticket_text": "ticket"},
        "outputs": {"category": "label"},
    },
    "split_fractions": {"train": 0.6, "val": 0.2, "test": 0.2},
    "shuffle": True,
    "seed": 42,
    "model_config": {"name": "openai/gpt-4o-mini", "temperature": 0.1},
}


def _wait_until(pred: Callable[[], bool], timeout: float = 8.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Pain-point collector
# ---------------------------------------------------------------------------
class UXFinding:
    def __init__(self, endpoint: str, severity: str, description: str, detail: str = ""):
        self.endpoint = endpoint
        self.severity = severity  # "critical", "major", "minor", "info"
        self.description = description
        self.detail = detail

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.endpoint}: {self.description}"


findings: List[UXFinding] = []


def note(endpoint: str, severity: str, desc: str, detail: str = ""):
    findings.append(UXFinding(endpoint, severity, desc, detail))


# ---------------------------------------------------------------------------
# Test: Full user journey
# ---------------------------------------------------------------------------
def test_full_ux_journey(configured_env) -> None:
    app = create_app(service=RealisticClassificationService())

    with TestClient(app) as client:
        # ===== 1. Health check =====
        health = client.get("/health")
        assert health.status_code == 200
        hbody = health.json()
        assert hbody["status"] == "ok"
        # Check: does health tell users what modules/optimizers are available?
        assets = hbody.get("registered_assets", {})
        if not assets.get("modules") and not assets.get("optimizers"):
            note("/health", "minor",
                 "registered_assets is empty — no hints about available modules/optimizers",
                 f"assets={assets}")

        # ===== 2. Queue check before submission =====
        queue_before = client.get("/queue")
        assert queue_before.status_code == 200

        # ===== 3. Submit realistic job =====
        submit = client.post("/run", json=REALISTIC_PAYLOAD)
        assert submit.status_code == 201, f"Submit failed: {submit.text}"
        submit_body = submit.json()
        job_id = submit_body["job_id"]

        # Check submission response fields
        assert submit_body["status"] == "pending"
        assert submit_body["username"] == "support_team"
        assert submit_body["module_name"] == "cot"
        assert submit_body["optimizer_name"] == "dspy.BootstrapFewShot"

        # UX: Does submission response include estimated info?
        if "estimated_remaining" not in submit_body:
            note("POST /run", "info",
                 "Submission response has no estimated_remaining field",
                 "Expected — job hasn't started yet")
        if "elapsed" not in submit_body:
            note("POST /run", "info",
                 "Submission response has no elapsed field",
                 "Expected — job hasn't started yet")

        # ===== 4. Poll status transitions =====
        statuses_seen = [submit_body["status"]]
        summaries_collected = []
        deadline = time.time() + 12

        while time.time() < deadline:
            summary = client.get(f"/jobs/{job_id}/summary")
            assert summary.status_code == 200
            sbody = summary.json()
            summaries_collected.append(sbody)

            current_status = sbody["status"]
            if current_status != statuses_seen[-1]:
                statuses_seen.append(current_status)

            if current_status == "success":
                break
            time.sleep(0.05)

        assert statuses_seen[-1] == "success", f"Job did not complete. Statuses: {statuses_seen}"

        # Check status transitions are logical
        assert "pending" in statuses_seen
        # UX: Did we see validating and running?
        if "validating" not in statuses_seen:
            note("GET /jobs/{id}/summary", "minor",
                 "Never observed 'validating' status — transitions too fast for polling",
                 f"Statuses seen: {statuses_seen}")
        if "running" not in statuses_seen:
            note("GET /jobs/{id}/summary", "minor",
                 "Never observed 'running' status — transitions too fast for polling",
                 f"Statuses seen: {statuses_seen}")

        # ===== 5. Check summary response fields =====
        final_summary = summaries_collected[-1]

        # Timing fields
        assert final_summary["elapsed"] is not None, "elapsed should be set for completed job"
        assert ":" in final_summary["elapsed"], f"elapsed not HH:MM:SS: {final_summary['elapsed']}"

        # estimated_remaining should be null for completed jobs (fixed)
        assert final_summary["estimated_remaining"] is None, \
            f"estimated_remaining should be null for completed job, got: {final_summary['estimated_remaining']}"

        # Check overview fields are populated
        assert final_summary["username"] == "support_team"
        assert final_summary["module_name"] == "cot"
        assert final_summary["optimizer_name"] == "dspy.BootstrapFewShot"
        assert final_summary["model_name"] == "openai/gpt-4o-mini"

        # UX: Are dataset_rows and column_mapping visible in summary?
        if final_summary.get("dataset_rows") is None:
            note("GET /jobs/{id}/summary", "major",
                 "dataset_rows is null — user can't see dataset size in summary")
        if final_summary.get("column_mapping") is None:
            note("GET /jobs/{id}/summary", "major",
                 "column_mapping is null — user can't see field mapping in summary")

        # Check progress/log counts
        assert isinstance(final_summary["progress_count"], int)
        assert isinstance(final_summary["log_count"], int)

        # UX: Are optimizer_kwargs visible?
        if not final_summary.get("optimizer_kwargs"):
            note("GET /jobs/{id}/summary", "minor",
                 "optimizer_kwargs empty — user can't see optimization settings in summary")

        # ===== 6. Full job detail =====
        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        dbody = detail.json()

        assert dbody["status"] == "success"
        assert dbody["result"] is not None

        # Check result quality fields
        result = dbody["result"]
        assert result["module_name"] == "cot"
        assert result["optimizer_name"] == "dspy.BootstrapFewShot"
        assert result["metric_name"] == "metric"
        assert result["split_counts"]["train"] == 3
        assert result["baseline_test_metric"] == 0.6
        assert result["optimized_test_metric"] == 0.9
        assert result["metric_improvement"] == 0.3
        assert result["runtime_seconds"] is not None

        # UX: elapsed and timing in detail
        assert dbody["elapsed"] is not None
        assert ":" in dbody["elapsed"]

        # Check latest_metrics has tqdm data
        metrics = dbody.get("latest_metrics", {})
        if "tqdm_remaining" in metrics:
            note("GET /jobs/{id}", "info",
                 f"latest_metrics still has tqdm_remaining={metrics['tqdm_remaining']} after completion",
                 "This is the last captured tqdm state — expected behavior")

        # Check progress_events
        progress = dbody.get("progress_events", [])
        if not progress:
            note("GET /jobs/{id}", "major",
                 "progress_events is empty — no optimization progress history available")

        # Check logs
        logs = dbody.get("logs", [])
        if not logs:
            note("GET /jobs/{id}", "minor",
                 "logs is empty — no log lines captured for the job")
        else:
            # Check log structure
            for log in logs:
                assert "timestamp" in log
                assert "level" in log
                assert "message" in log
                assert "logger" in log

        # ===== 7. Logs endpoint =====
        logs_resp = client.get(f"/jobs/{job_id}/logs")
        assert logs_resp.status_code == 200
        log_entries = logs_resp.json()
        assert isinstance(log_entries, list)

        # UX: Check if logs have useful content
        if log_entries:
            messages = [e["message"] for e in log_entries]
            has_start = any("start" in m.lower() or "optimization" in m.lower() for m in messages)
            has_finish = any("complete" in m.lower() or "finish" in m.lower() for m in messages)
            if not has_start:
                note("GET /jobs/{id}/logs", "info",
                     "No log entry indicates optimization start")
            if not has_finish:
                note("GET /jobs/{id}/logs", "info",
                     "No log entry indicates optimization completion")

        # ===== 8. Artifact endpoint =====
        artifact = client.get(f"/jobs/{job_id}/artifact")
        assert artifact.status_code == 200
        abody = artifact.json()
        # Result from mock has no artifact — check graceful handling
        if abody.get("program_artifact") is None:
            note("GET /jobs/{id}/artifact", "info",
                 "program_artifact is null — mock service didn't produce one",
                 "In production, this would contain the optimized program pickle")

        # ===== 9. Jobs listing (paginated) =====
        listing = client.get("/jobs", params={"username": "support_team"})
        assert listing.status_code == 200
        listing_body = listing.json()
        assert "items" in listing_body
        assert "total" in listing_body
        assert "limit" in listing_body
        assert "offset" in listing_body
        assert listing_body["total"] >= 1

        jobs = listing_body["items"]
        assert len(jobs) >= 1

        job_entry = jobs[0]
        assert job_entry["job_id"] == job_id
        assert job_entry["username"] == "support_team"
        assert job_entry["status"] == "success"
        assert isinstance(job_entry["progress_count"], int)
        assert isinstance(job_entry["log_count"], int)

        # Check listing has enough info for a dashboard
        missing_in_listing = []
        for field in ["elapsed", "module_name", "optimizer_name", "model_name",
                       "dataset_rows"]:
            if job_entry.get(field) is None:
                missing_in_listing.append(field)
        if missing_in_listing:
            note("GET /jobs", "major",
                 f"Listing is missing dashboard fields: {missing_in_listing}",
                 "Users need these to identify jobs in a list view")

        # Check result metrics are in listing (baseline/optimized)
        if job_entry.get("baseline_test_metric") is not None:
            assert job_entry["baseline_test_metric"] == 0.6
        if job_entry.get("optimized_test_metric") is not None:
            assert job_entry["optimized_test_metric"] == 0.9

        # ===== 10. Pagination =====
        page1 = client.get("/jobs", params={"limit": 1, "offset": 0})
        assert page1.status_code == 200
        p1body = page1.json()
        assert len(p1body["items"]) <= 1
        assert p1body["total"] >= 1
        assert p1body["limit"] == 1
        assert p1body["offset"] == 0

        # ===== 11. Queue status =====
        queue = client.get("/queue")
        assert queue.status_code == 200
        qbody = queue.json()
        assert "pending_jobs" in qbody
        assert "active_jobs" in qbody
        assert "worker_threads" in qbody
        assert "workers_alive" in qbody

        # ===== 12. Submit a second job to test multi-job listing =====
        submit2 = client.post("/run", json={
            **REALISTIC_PAYLOAD,
            "username": "other_team",
        })
        assert submit2.status_code == 201
        job_id_2 = submit2.json()["job_id"]

        assert _wait_until(
            lambda: client.get(f"/jobs/{job_id_2}/summary").json()["status"] == "success",
            timeout=12
        )

        # Test filtering by status
        all_jobs = client.get("/jobs", params={"status": "success"})
        assert all_jobs.status_code == 200
        assert all(j["status"] == "success" for j in all_jobs.json()["items"])

        # Test filtering by username
        user_jobs = client.get("/jobs", params={"username": "support_team"})
        assert user_jobs.status_code == 200
        assert all(j["username"] == "support_team" for j in user_jobs.json()["items"])

        # ===== 13. Error handling: bad payload =====
        bad_payload = dict(REALISTIC_PAYLOAD)
        bad_payload["dataset"] = []  # empty dataset
        bad_submit = client.post("/run", json=bad_payload)
        assert bad_submit.status_code == 422
        err_body = bad_submit.json()
        # UX: Check error structure
        if "detail" in err_body:
            # Check if error messages are user-friendly
            if isinstance(err_body["detail"], list):
                for issue in err_body["detail"]:
                    if "field" not in issue:
                        note("POST /run (422)", "minor",
                             "Validation error missing 'field' key",
                             f"Error: {issue}")
        elif "error" in err_body:
            detail = err_body.get("detail", [])
            if isinstance(detail, list) and detail:
                assert "field" in detail[0], "Validation errors should include field paths"

        # ===== 14. Error handling: missing required fields =====
        minimal_bad = {"username": "test"}
        bad_submit2 = client.post("/run", json=minimal_bad)
        assert bad_submit2.status_code == 422

        # ===== 15. Error handling: nonexistent job =====
        not_found = client.get("/jobs/nonexistent-id-12345")
        assert not_found.status_code == 404

        not_found_summary = client.get("/jobs/nonexistent-id-12345/summary")
        assert not_found_summary.status_code == 404

        not_found_logs = client.get("/jobs/nonexistent-id-12345/logs")
        assert not_found_logs.status_code == 404

        not_found_artifact = client.get("/jobs/nonexistent-id-12345/artifact")
        assert not_found_artifact.status_code == 404

        # ===== 16. Delete a completed job =====
        delete_resp = client.delete(f"/jobs/{job_id_2}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True

        # Verify it's gone
        gone = client.get(f"/jobs/{job_id_2}")
        assert gone.status_code == 404

        # ===== 17. Delete an active job should fail =====
        # Submit a new job and try to delete while pending
        submit3 = client.post("/run", json=REALISTIC_PAYLOAD)
        assert submit3.status_code == 201
        job_id_3 = submit3.json()["job_id"]

        # Try to delete immediately (should be pending/validating/running)
        delete_active = client.delete(f"/jobs/{job_id_3}")
        if delete_active.status_code == 409:
            pass  # correct - cannot delete active job
        elif delete_active.status_code == 200:
            note("DELETE /jobs/{id}", "major",
                 "Was able to delete a non-terminal job",
                 "This could orphan worker threads")

        # Clean up job_id_3
        _wait_until(
            lambda: client.get(f"/jobs/{job_id_3}/summary").json().get("status") in ("success", "failed"),
            timeout=12
        )

        # ===== 18. Cancel + re-cancel =====
        submit4 = client.post("/run", json=REALISTIC_PAYLOAD)
        assert submit4.status_code == 201
        job_id_4 = submit4.json()["job_id"]

        cancel = client.post(f"/jobs/{job_id_4}/cancel")
        assert cancel.status_code == 200

        # Wait for deletion
        _wait_until(lambda: client.get(f"/jobs/{job_id_4}").status_code == 404, timeout=3)

        # Cancel again should 404
        cancel_again = client.post(f"/jobs/{job_id_4}/cancel")
        assert cancel_again.status_code == 404

        # ===== 19. Artifact on non-success job =====
        # Submit and cancel to get a non-success state
        submit5 = client.post("/run", json=REALISTIC_PAYLOAD)
        assert submit5.status_code == 201
        job_id_5 = submit5.json()["job_id"]

        # Let it start running, then cancel
        _wait_until(
            lambda: client.get(f"/jobs/{job_id_5}/summary").json()["status"] in ("running", "validating"),
            timeout=8
        )
        client.post(f"/jobs/{job_id_5}/cancel")

        # Artifact should be 404 or 409
        _wait_until(
            lambda: client.get(f"/jobs/{job_id_5}").status_code in (200, 404),
            timeout=3
        )
        art_resp = client.get(f"/jobs/{job_id_5}/artifact")
        assert art_resp.status_code in (404, 409)

    # ===== Print UX Findings =====
    print("\n" + "=" * 70)
    print("UX JOURNEY FINDINGS")
    print("=" * 70)
    for i, f in enumerate(findings, 1):
        print(f"\n{i}. [{f.severity.upper()}] {f.endpoint}")
        print(f"   {f.description}")
        if f.detail:
            print(f"   Detail: {f.detail}")
    print(f"\nTotal findings: {len(findings)}")
    print("=" * 70)

    # All remaining findings are INFO-level (expected behavior)
    assert all(f.severity in ("info", "minor") for f in findings), \
        f"Unexpected major findings: {[f for f in findings if f.severity not in ('info', 'minor')]}"
