"""Tests for the Google-Drive-style optimization sharing router.

Exercises the owner/editor-gated management surface (general-access policy,
member CRUD, role gating), the access-gated public composite read
(``GET /share/{token}``), and the viewer+-only inference path
(``POST /share/{token}/serve``).

The store mirrors the in-memory SQLite pattern of the sibling routers: a
``RemoteDBJobStore`` subclass that skips the pgvector bootstrap and seeds
``JobModel`` rows directly. The serve test monkeypatches the program loader and
language-model builder on the ``share`` module so it never touches a real model.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ...models import RunResponse, ServeInfoResponse
from ...storage.models import Base, JobModel
from ...storage.remote import RemoteDBJobStore
from ..auth import AuthenticatedUser, get_authenticated_user
from ..routers import share as share_module
from ..routers.share import create_share_router, get_optional_user
from .mocks import make_artifact, make_run_result


class _MemStore(RemoteDBJobStore):
    """In-memory SQLite job store for share-router tests (skips pgvector bootstrap)."""

    def __init__(self) -> None:
        """Build an in-memory SQLite engine and create the ORM tables."""
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)


def _seed_job(store: _MemStore, optimization_id: str = "opt-share-1", username: str = "alice") -> None:
    """Insert a successful job owned by ``username`` carrying secrets to scrub.

    Args:
        store: The in-memory store to seed into.
        optimization_id: Optimization id for the seeded job.
        username: Owner username recorded on the job.
    """
    with Session(store.engine) as session:
        session.add(
            JobModel(
                optimization_id=optimization_id,
                status="success",
                created_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                latest_metrics={},
                result=None,
                payload_overview={
                    "optimization_type": "run",
                    "name": "My run",
                    "username": username,
                    "optimizer_name": "gepa",
                    "module_name": "predict",
                },
                payload={
                    "username": username,
                    "signature_code": "class S(dspy.Signature): ...",
                    "metric_code": "def metric(gold, pred, trace=None): return 1.0",
                    "optimizer_name": "gepa",
                    "module_name": "predict",
                    "column_mapping": {"inputs": {"question": "question"}, "outputs": {"answer": "answer"}},
                    "split_fractions": {"train": 0.6, "val": 0.2, "test": 0.2},
                    "shuffle": True,
                    "seed": 42,
                    "dataset": [{"question": f"q{i}", "answer": f"a{i}"} for i in range(40)],
                    "model_config": {
                        "name": "openai/gpt-5.4-nano",
                        "base_url": "https://secret.internal",
                        "extra": {"api_key": "sk-SECRET", "reasoning_effort": "medium"},
                    },
                    "reflection_model_config": {
                        "name": "openai/gpt-5.4-nano",
                        "extra": {"api_key": "sk-SECRET2"},
                    },
                },
                username=username,
            )
        )
        session.commit()


def _client(store: _MemStore, user: str | None = "alice") -> TestClient:
    """Build a TestClient over the share router, optionally authed as ``user``.

    The public share routes resolve the caller via ``get_optional_user`` (which
    inspects the Authorization header and so cannot see a ``get_authenticated_user``
    override), so both dependencies are overridden: management routes read the
    former, the public ``/share`` routes read the latter. ``None`` leaves the
    caller anonymous (``get_optional_user`` returns ``None``).

    Args:
        store: Job store wired into the router factory.
        user: Username to authenticate as, or ``None`` for an anonymous client.

    Returns:
        A ``TestClient`` over a minimal app mounting only the share router.
    """
    app = FastAPI()
    app.include_router(create_share_router(job_store=store))
    if user is not None:
        identity = AuthenticatedUser(username=user, role="user", groups=())
        app.dependency_overrides[get_authenticated_user] = lambda: identity
        app.dependency_overrides[get_optional_user] = lambda: identity
    return TestClient(app, raise_server_exceptions=False)


def _enable_anyone(store: _MemStore, optimization_id: str = "opt-share-1", user: str = "alice") -> str:
    """Set ``general_access`` to ``anyone`` and return the minted token.

    Args:
        store: The seeded store.
        optimization_id: Optimization to switch to an anyone-link.
        user: Owner/editor making the change.

    Returns:
        The active share token.
    """
    owner = _client(store, user=user)
    resp = owner.put(f"/optimizations/{optimization_id}/sharing", json={"general_access": "anyone"})
    assert resp.status_code == 200
    return resp.json()["token"]


def test_put_general_access_toggles_restricted_and_anyone() -> None:
    """The owner can flip general access between restricted and anyone, keeping the token."""
    store = _MemStore()
    _seed_job(store)
    owner = _client(store, user="alice")

    to_anyone = owner.put("/optimizations/opt-share-1/sharing", json={"general_access": "anyone"})
    assert to_anyone.status_code == 200
    body = to_anyone.json()
    assert body["general_access"] == "anyone"
    token = body["token"]
    assert token
    assert body["share_path"] == f"/share/{token}"
    assert body["owner"] == "alice"

    back = owner.put("/optimizations/opt-share-1/sharing", json={"general_access": "restricted"})
    assert back.status_code == 200
    assert back.json()["general_access"] == "restricted"
    assert back.json()["token"] == token


def test_put_invalid_general_access_400() -> None:
    """An unknown general-access value is rejected with 400."""
    store = _MemStore()
    _seed_job(store)
    owner = _client(store, user="alice")
    assert owner.put("/optimizations/opt-share-1/sharing", json={"general_access": "public"}).status_code == 400


def test_get_sharing_non_owner_404() -> None:
    """A stranger cannot read the sharing config (existence is not leaked)."""
    store = _MemStore()
    _seed_job(store, username="alice")
    stranger = _client(store, user="bob")
    assert stranger.get("/optimizations/opt-share-1/sharing").status_code == 404


def test_anonymous_get_anyone_link_view_role_hides_owner_and_serve_info() -> None:
    """Anonymous read of an anyone-link resolves to view: owner null, serve_info null."""
    store = _MemStore()
    _seed_job(store, username="alice")
    token = _enable_anyone(store)

    public = _client(store, user=None)
    resp = public.get(f"/share/{token}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["role"] == "view"
    assert body["owner"] is None
    assert body["serve_info"] is None
    assert body["status"]["username"] is None


def test_anonymous_get_restricted_link_404() -> None:
    """Anonymous read of a restricted optimization 404s (no anyone fallback)."""
    store = _MemStore()
    _seed_job(store, username="alice")
    # A token exists but general access stays restricted.
    owner = _client(store, user="alice")
    token = owner.put("/optimizations/opt-share-1/sharing", json={"general_access": "restricted"}).json()["token"]

    public = _client(store, user=None)
    assert public.get(f"/share/{token}").status_code == 404


def test_member_viewer_sees_owner_and_serve_info() -> None:
    """A viewer member sees the real owner; serve_info is populated for viewer+."""
    store = _MemStore()
    _seed_job(store, username="alice")
    token = _enable_anyone(store)

    owner = _client(store, user="alice")
    assert owner.post(
        "/optimizations/opt-share-1/sharing/members", json={"username": "carol", "role": "viewer"}
    ).status_code == 200

    info = ServeInfoResponse(
        optimization_id="opt-share-1",
        module_name="predict",
        optimizer_name="gepa",
        model_name="openai/gpt-5.4-nano",
        input_fields=["question"],
        output_fields=["answer"],
        instructions="Be helpful.",
        demo_count=0,
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(share_module, "_serve_info", lambda *_args, **_kw: info)
        viewer = _client(store, user="carol")
        resp = viewer.get(f"/share/{token}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "viewer"
    assert body["owner"] == "alice"
    assert body["serve_info"]["input_fields"] == ["question"]
    assert body["status"]["username"] == "alice"


def test_public_view_payload_is_scrubbed() -> None:
    """The public payload strips username, raw dataset, api_key and base_url."""
    store = _MemStore()
    _seed_job(store, username="alice")
    token = _enable_anyone(store)

    public = _client(store, user=None)
    body = public.get(f"/share/{token}").json()
    payload = body["payload"]

    assert payload["signature_code"].startswith("class S")
    assert "username" not in payload
    assert "dataset" not in payload
    assert "base_url" not in payload["model_config"]
    assert "api_key" not in payload["model_config"]["extra"]
    assert payload["model_config"]["extra"]["reasoning_effort"] == "medium"
    assert "api_key" not in payload["reflection_model_config"]["extra"]


def test_public_view_dataset_is_full_not_capped() -> None:
    """The shared dataset returns the FULL split (all 40 rows), not a preview cap."""
    store = _MemStore()
    _seed_job(store, username="alice")
    token = _enable_anyone(store)

    public = _client(store, user=None)
    body = public.get(f"/share/{token}").json()
    dataset = body["dataset"]

    assert dataset["total_rows"] == 40
    counts = dataset["split_counts"]
    assert counts["train"] + counts["val"] + counts["test"] == 40
    rows = sum(len(dataset["splits"][s]) for s in ("train", "val", "test"))
    assert rows == 40


def test_member_crud_add_patch_remove() -> None:
    """A member grant can be added, re-roled, and removed by the owner."""
    store = _MemStore()
    _seed_job(store, username="alice")
    owner = _client(store, user="alice")

    added = owner.post(
        "/optimizations/opt-share-1/sharing/members", json={"username": "Dave", "role": "viewer"}
    )
    assert added.status_code == 200
    assert {"username": "dave", "role": "viewer"} in added.json()["members"]

    patched = owner.patch("/optimizations/opt-share-1/sharing/members/dave", json={"role": "editor"})
    assert patched.status_code == 200
    assert {"username": "dave", "role": "editor"} in patched.json()["members"]

    removed = owner.delete("/optimizations/opt-share-1/sharing/members/dave")
    assert removed.status_code == 200
    assert removed.json()["members"] == []


def test_member_add_invalid_role_400() -> None:
    """An invalid member role is rejected with 400."""
    store = _MemStore()
    _seed_job(store, username="alice")
    owner = _client(store, user="alice")
    resp = owner.post(
        "/optimizations/opt-share-1/sharing/members", json={"username": "dave", "role": "view"}
    )
    assert resp.status_code == 400


def test_member_patch_unknown_member_404() -> None:
    """Patching a non-existent member returns 404."""
    store = _MemStore()
    _seed_job(store, username="alice")
    owner = _client(store, user="alice")
    assert owner.patch(
        "/optimizations/opt-share-1/sharing/members/ghost", json={"role": "editor"}
    ).status_code == 404


def test_member_management_gated_for_non_owner_404() -> None:
    """A stranger cannot add members (404 — owner existence is not leaked)."""
    store = _MemStore()
    _seed_job(store, username="alice")
    stranger = _client(store, user="bob")
    assert stranger.post(
        "/optimizations/opt-share-1/sharing/members", json={"username": "dave", "role": "viewer"}
    ).status_code == 404


def test_viewer_member_cannot_manage_sharing_404() -> None:
    """A viewer-tier member lacks manage access and 404s on member endpoints."""
    store = _MemStore()
    _seed_job(store, username="alice")
    owner = _client(store, user="alice")
    owner.post("/optimizations/opt-share-1/sharing/members", json={"username": "carol", "role": "viewer"})

    viewer = _client(store, user="carol")
    assert viewer.get("/optimizations/opt-share-1/sharing").status_code == 404
    assert viewer.post(
        "/optimizations/opt-share-1/sharing/members", json={"username": "dave", "role": "viewer"}
    ).status_code == 404


def test_editor_member_can_manage_sharing() -> None:
    """An editor-tier member can read and mutate the sharing config."""
    store = _MemStore()
    _seed_job(store, username="alice")
    owner = _client(store, user="alice")
    owner.post("/optimizations/opt-share-1/sharing/members", json={"username": "erin", "role": "editor"})

    editor = _client(store, user="erin")
    assert editor.get("/optimizations/opt-share-1/sharing").status_code == 200
    added = editor.post(
        "/optimizations/opt-share-1/sharing/members", json={"username": "dave", "role": "viewer"}
    )
    assert added.status_code == 200
    assert {"username": "dave", "role": "viewer"} in added.json()["members"]


def test_unknown_token_404() -> None:
    """An unknown share token returns 404."""
    store = _MemStore()
    public = _client(store, user=None)
    assert public.get("/share/does-not-exist").status_code == 404


def test_user_search_matches_prefix() -> None:
    """The username autocomplete returns distinct known usernames by prefix."""
    store = _MemStore()
    _seed_job(store, optimization_id="opt-a", username="alice")
    _seed_job(store, optimization_id="opt-al", username="albert")
    _seed_job(store, optimization_id="opt-b", username="bob")
    caller = _client(store, user="alice")

    resp = caller.get("/users/search", params={"q": "al"})
    assert resp.status_code == 200
    names = resp.json()["usernames"]
    assert "alice" in names
    assert "albert" in names
    assert "bob" not in names


class _FakePrediction:
    """Stub prediction exposing attribute access for the declared output field."""

    answer: str = "shared-answer"


def _seed_serveable(store: _MemStore, optimization_id: str = "opt-share-1") -> tuple[object, object, dict]:
    """Return the ``(program, RunResponse, overview)`` triple a fake loader yields.

    Builds a single-run result whose artifact declares one input and one output
    field so the serve handler's input validation and output projection both
    exercise the happy path without a real model.

    Args:
        store: The seeded store (unused beyond signature symmetry with loaders).
        optimization_id: Optimization id embedded in the synthesized result.

    Returns:
        A ``(program, RunResponse, overview)`` tuple matching ``load_program``.
    """
    artifact = make_artifact(input_fields=["question"], output_fields=["answer"])
    result: RunResponse = make_run_result(artifact)
    overview = {
        "module_name": "predict",
        "optimizer_name": "gepa",
        "model_name": "openai/gpt-5.4-nano",
    }
    program = lambda **_inputs: _FakePrediction()  # noqa: E731 — terse stub program
    return program, result, overview


def test_serve_allowed_for_viewer_member() -> None:
    """A viewer member can run inference; the owner key is used server-side."""
    store = _MemStore()
    _seed_job(store, username="alice")
    token = _enable_anyone(store)
    owner = _client(store, user="alice")
    owner.post("/optimizations/opt-share-1/sharing/members", json={"username": "carol", "role": "viewer"})

    program, result, overview = _seed_serveable(store)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(share_module, "load_program", lambda *_a, **_k: (program, result, overview))
        mp.setattr(share_module, "build_language_model", lambda _cfg: object())
        mp.setattr(share_module.dspy, "context", lambda **_kw: nullcontext())
        viewer = _client(store, user="carol")
        resp = viewer.post(f"/share/{token}/serve", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 200
    body = resp.json()
    assert body["optimization_id"] == "opt-share-1"
    assert body["outputs"]["answer"] == "shared-answer"
    assert body["input_fields"] == ["question"]
    # The owner's secret key/base_url must never surface in the serve response.
    assert "sk-SECRET" not in resp.text
    assert "secret.internal" not in resp.text


def test_serve_forbidden_for_anonymous_view_role() -> None:
    """An anonymous view-role caller is forbidden from inference (403)."""
    store = _MemStore()
    _seed_job(store, username="alice")
    token = _enable_anyone(store)

    public = _client(store, user=None)
    resp = public.post(f"/share/{token}/serve", json={"inputs": {"question": "hi"}})
    assert resp.status_code == 403
