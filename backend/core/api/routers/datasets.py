"""Routes for dataset profiling, split-plan recommendations, and demo samples.

``POST /datasets/profile`` — inspect the uploaded rows and return a
``DatasetProfile`` plus a recommended ``SplitPlan``. Purely advisory:
the caller either accepts the plan's fractions on the subsequent
``/run`` or ``/grid-search`` submission, or overrides them manually.

``GET /datasets/samples`` / ``POST /datasets/samples/{id}/stage`` —
curated demo datasets the agent can stage into the wizard in one step
so non-technical users can try the product end-to-end with zero setup.

``POST /datasets/column-roles`` — validate a proposed column-role map
and return a ``wizard_state`` patch so the agent can configure column
roles on the user's behalf.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...i18n import SAMPLE_DATASETS
from ...models import ProfileDatasetRequest, ProfileDatasetResponse
from ...service_gateway.datasets.planner import recommend_split
from ...service_gateway.datasets.profiler import profile_dataset
from ..errors import DomainError


class SampleDatasetSummary(BaseModel):
    """Metadata for one curated sample in the ``GET /datasets/samples`` list."""

    sample_id: str
    name: str
    description: str
    task_type: str
    row_count: int
    columns: list[str]


class SampleDatasetListResponse(BaseModel):
    """Envelope for ``GET /datasets/samples`` — the catalog of bundled samples."""

    samples: list[SampleDatasetSummary]


class SampleDatasetStageResponse(BaseModel):
    """Envelope for ``POST /datasets/samples/{id}/stage`` — rows + wizard patch."""

    sample_id: str
    name: str
    description: str
    dataset: list[dict[str, Any]]
    dataset_filename: str
    wizard_state: dict[str, Any]


class ColumnRolesRequest(BaseModel):
    """Request body for ``POST /datasets/column-roles``."""

    dataset_columns: list[str] = Field(min_length=1, max_length=100)
    column_roles: dict[str, str] = Field(
        description="Map of dataset column name → role: 'input', 'output', or 'ignore'.",
    )
    job_name: str | None = Field(default=None, max_length=200)


class ColumnRolesResponse(BaseModel):
    """Envelope for ``POST /datasets/column-roles`` — validated roles + wizard patch."""

    wizard_state: dict[str, Any]


_VALID_COLUMN_ROLES = {"input", "output", "ignore"}


def create_datasets_router() -> APIRouter:
    """Build the datasets router.

    Returns:
        A configured :class:`APIRouter` exposing the dataset profile, sample,
        and column-roles endpoints.
    """
    router = APIRouter()

    @router.post(
        "/datasets/profile",
        response_model=ProfileDatasetResponse,
        summary="Profile a dataset and recommend a split plan",
        tags=["agent"],
    )
    def profile(payload: ProfileDatasetRequest) -> ProfileDatasetResponse:
        """Return a ``DatasetProfile`` and a recommended ``SplitPlan``.

        The profiler walks the rows once to compute size, duplicate count,
        and primary-target stats. The planner then picks train/val/test
        fractions tuned to the size tier. Users can accept the plan or
        override ``split_fractions`` when submitting the actual optimization.

        Errors: 400 (empty dataset), 422 (malformed body).

        Args:
            payload: Profiling request with dataset rows, column mapping, and seed.

        Returns:
            A :class:`ProfileDatasetResponse` containing the profile and the
            recommended split plan.
        """
        dataset_profile = profile_dataset(payload.dataset, payload.column_mapping)
        plan = recommend_split(dataset_profile, seed=payload.seed)
        return ProfileDatasetResponse(profile=dataset_profile, plan=plan)

    @router.get(
        "/datasets/samples",
        response_model=SampleDatasetListResponse,
        summary="List curated sample datasets the agent can stage",
        tags=["agent"],
    )
    def list_sample_datasets() -> SampleDatasetListResponse:
        """Return the catalog of bundled demo datasets without the rows.

        The catalog is small and static — suited for first-run demos where
        the user doesn't have a dataset of their own yet. Use
        ``POST /datasets/samples/{sample_id}/stage`` to prefill the wizard.

        Returns:
            A :class:`SampleDatasetListResponse` containing one summary per sample.
        """
        summaries = [
            SampleDatasetSummary(
                sample_id=sample_id,
                name=sample["name"],
                description=sample["description"],
                task_type=sample["task_type"],
                row_count=len(sample["rows"]),
                columns=list(sample["input_columns"]) + list(sample["output_columns"]),
            )
            for sample_id, sample in SAMPLE_DATASETS.items()
        ]
        return SampleDatasetListResponse(samples=summaries)

    @router.post(
        "/datasets/samples/{sample_id}/stage",
        response_model=SampleDatasetStageResponse,
        summary="Stage a sample dataset into the submit wizard",
        tags=["agent"],
    )
    def stage_sample_dataset(sample_id: str) -> SampleDatasetStageResponse:
        """Return the sample rows plus a ``wizard_state`` patch ready to submit.

        Populates dataset_ready, columns_configured, dataset_columns,
        column_roles, signature_code, metric_code, and a default job_name
        so a non-technical user can hit "run" without writing code.

        Args:
            sample_id: Identifier of the bundled sample dataset.

        Returns:
            A :class:`SampleDatasetStageResponse` with rows, filename, and
            wizard-state patch.

        Raises:
            DomainError: 404 when ``sample_id`` is unknown.
        """
        sample = SAMPLE_DATASETS.get(sample_id)
        if sample is None:
            raise DomainError(
                "dataset.sample_unknown",
                status=404,
                sample_id=sample_id,
            )

        columns = list(sample["input_columns"]) + list(sample["output_columns"])
        column_roles: dict[str, str] = {}
        for col in sample["input_columns"]:
            column_roles[col] = "input"
        for col in sample["output_columns"]:
            column_roles[col] = "output"

        wizard_state: dict[str, Any] = {
            "dataset_ready": True,
            "columns_configured": True,
            "dataset_columns": columns,
            "column_roles": column_roles,
            "signature_code": sample["signature_code"],
            "metric_code": sample["metric_code"],
            "job_name": sample["name"],
        }

        return SampleDatasetStageResponse(
            sample_id=sample_id,
            name=sample["name"],
            description=sample["description"],
            dataset=sample["rows"],
            dataset_filename=sample["dataset_filename"],
            wizard_state=wizard_state,
        )

    @router.post(
        "/datasets/column-roles",
        response_model=ColumnRolesResponse,
        summary="Validate a column-role map and project it into the wizard",
        tags=["agent"],
    )
    def set_column_roles(req: ColumnRolesRequest) -> ColumnRolesResponse:
        """Validate a proposed column-role map and return a ``wizard_state`` patch.

        Every column in ``column_roles`` must be listed in
        ``dataset_columns`` and have role ``input``, ``output``, or
        ``ignore``. At least one input and one output are required.
        On success the response contains a wizard_state patch with
        ``columns_configured`` set to true, the role map, and an
        optional ``job_name``.

        Args:
            req: Request body with the dataset columns, role map, and an
                optional job name.

        Returns:
            A :class:`ColumnRolesResponse` with the wizard-state patch.

        Raises:
            DomainError: 422 when a column is unknown, a role is invalid, or
                no input/output role is supplied.
        """
        columns_set = set(req.dataset_columns)
        unknown = [col for col in req.column_roles if col not in columns_set]
        if unknown:
            raise DomainError(
                "dataset.column_roles_unknown",
                status=422,
                unknown=sorted(unknown),
            )
        bad_roles = {col: role for col, role in req.column_roles.items() if role not in _VALID_COLUMN_ROLES}
        if bad_roles:
            raise DomainError(
                "dataset.column_roles_invalid",
                status=422,
                bad=bad_roles,
            )
        inputs = [col for col, role in req.column_roles.items() if role == "input"]
        outputs = [col for col, role in req.column_roles.items() if role == "output"]
        if not inputs:
            raise DomainError("dataset.column_roles_need_input", status=422)
        if not outputs:
            raise DomainError("dataset.column_roles_need_output", status=422)

        wizard_state: dict[str, Any] = {
            "dataset_columns": req.dataset_columns,
            "column_roles": dict(req.column_roles),
            "columns_configured": True,
        }
        if req.job_name is not None and req.job_name.strip():
            wizard_state["job_name"] = req.job_name.strip()

        return ColumnRolesResponse(wizard_state=wizard_state)

    return router
