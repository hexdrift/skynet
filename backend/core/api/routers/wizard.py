"""Routes for agent-driven wizard-state mutation.

``POST /wizard/update`` is the single endpoint the generalist agent uses
to edit any subset of wizard fields in one call. Each supplied field is
validated against a narrow whitelist and echoed back in a
``wizard_state`` patch that the frontend mirrors into the live submit
wizard (see ``use-submit-wizard.ts`` pulse-apply effect).

The endpoint is intentionally broad: it supersedes the per-field tools
(``set_column_roles``, etc.) while staying additive — those legacy tools
still work. An agent can call this once per turn with a composite patch
(e.g. optimizer + split + kwargs) instead of chaining several narrow calls.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from ..errors import DomainError

_VALID_COLUMN_ROLES = frozenset({"input", "output", "ignore"})


class WizardUpdateRequest(BaseModel):
    """Partial update for any subset of editable wizard fields.

    Every field is optional. Only supplied fields are validated and
    echoed into the ``wizard_state`` patch returned in the response.
    Fields not supplied are left untouched on the frontend.
    """

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    job_name: str | None = Field(default=None, max_length=200)
    job_description: str | None = Field(default=None, max_length=500)
    optimizer_name: str | None = Field(
        default=None,
        max_length=80,
        description="Optimizer algorithm, e.g. 'gepa', 'bootstrap_few_shot'.",
    )
    module_name: str | None = Field(
        default=None,
        max_length=80,
        description="DSPy module to optimize, e.g. 'predict', 'cot'.",
    )
    job_type: Literal["run", "grid_search"] | None = Field(
        default=None,
        description="'run' for a single-pair run, 'grid_search' for a model-pair sweep.",
    )

    column_roles: dict[str, str] | None = Field(
        default=None,
        description="Dataset column → role map. Values: 'input', 'output', or 'ignore'.",
    )

    primary_model: dict[str, Any] | None = Field(
        default=None,
        alias="model_config",
        description="Generation model config dict (name required, other fields optional).",
    )
    reflection_model: dict[str, Any] | None = Field(
        default=None,
        alias="reflection_model_config",
        description="Reflection model config dict (teacher for GEPA).",
    )

    generation_models: list[dict[str, Any]] | None = Field(
        default=None,
        description="Grid-search list of generation models.",
    )
    reflection_models: list[dict[str, Any]] | None = Field(
        default=None,
        description="Grid-search list of reflection models.",
    )
    use_all_generation_models: bool | None = Field(
        default=None,
        description="When true, sweep over every generation model in the catalog.",
    )
    use_all_reflection_models: bool | None = Field(
        default=None,
        description="When true, sweep over every reflection model in the catalog.",
    )

    split_fractions: dict[str, float] | None = Field(
        default=None,
        description="Train/val/test fractions. Must sum to 1.0 and be non-negative.",
    )
    split_mode: Literal["auto", "manual"] | None = Field(
        default=None,
        description="'auto' follows the profiler recommendation; 'manual' pins user edits.",
    )
    seed: int | None = Field(default=None, description="Shuffle/split seed.")
    shuffle: bool | None = Field(default=None)

    optimizer_kwargs: dict[str, Any] | None = Field(
        default=None,
        description=("Optimizer parameters. Known keys: auto, reflection_minibatch_size, max_full_evals, use_merge."),
    )

    signature_code: str | None = Field(
        default=None,
        description="Full DSPy Signature source to replace the current one.",
    )
    metric_code: str | None = Field(
        default=None,
        description="Full metric function source to replace the current one.",
    )


class WizardUpdateResponse(BaseModel):
    """Envelope returning the validated ``wizard_state`` patch."""

    wizard_state: dict[str, Any]


def _validate_model_dict(v: Any, field_name: str) -> dict[str, Any]:
    """Light-weight validation of a ``ModelConfig``-shaped dict.

    Allows partial dicts (``{"name": "openai/gpt-4o"}``) for progressive
    configuration.

    Args:
        v: Candidate model-config dict from the request.
        field_name: Field label used in error messages.

    Returns:
        A cleaned dict the frontend can merge into its local
        ``ModelConfig`` state via object spread.

    Raises:
        DomainError: 422 with a wizard-prefixed key when the input is not
            a JSON object or any field fails type validation.
    """
    if not isinstance(v, dict):
        raise DomainError("wizard.model_not_json_object", status=422, field=field_name)
    out: dict[str, Any] = {}
    name = v.get("name")
    if name is not None:
        if not isinstance(name, str) or not name.strip():
            raise DomainError("wizard.model_name_non_empty_string", status=422, field=field_name)
        out["name"] = name.strip()
    base_url = v.get("base_url")
    if base_url is not None:
        if not isinstance(base_url, str):
            raise DomainError("wizard.model_base_url_not_string", status=422, field=field_name)
        out["base_url"] = base_url
    for key in ("temperature", "top_p"):
        val = v.get(key)
        if val is not None:
            if not isinstance(val, (int, float)):
                raise DomainError(
                    "wizard.model_number_required",
                    status=422,
                    field=field_name,
                    key=key,
                )
            out[key] = float(val)
    max_tokens = v.get("max_tokens")
    if max_tokens is not None:
        if not isinstance(max_tokens, int):
            raise DomainError("wizard.model_max_tokens_int", status=422, field=field_name)
        out["max_tokens"] = max_tokens
    extra = v.get("extra")
    if extra is not None:
        if not isinstance(extra, dict):
            raise DomainError("wizard.model_extra_not_object", status=422, field=field_name)
        out["extra"] = extra
    return out


def create_wizard_router() -> APIRouter:
    """Build the wizard-state router.

    Returns:
        A FastAPI ``APIRouter`` exposing ``POST /wizard/update``.
    """
    router = APIRouter()

    @router.post(
        "/wizard/update",
        response_model=WizardUpdateResponse,
        status_code=200,
        operation_id="update_wizard_state",
        summary="Patch any subset of editable wizard fields",
        tags=["agent"],
    )
    def update_wizard_state(req: WizardUpdateRequest) -> WizardUpdateResponse:
        """Validate and echo any subset of wizard fields as a ``wizard_state`` patch.

        Covers every editable field in the submit wizard: job metadata,
        optimizer/module choice, column roles, primary & secondary model
        configs, grid-search model lists, split plan, and optimizer kwargs.
        Supply only the fields you want to change — the rest are left
        untouched on the frontend.

        Args:
            req: The partial-update body (every field optional).

        Returns:
            A ``WizardUpdateResponse`` carrying the validated patch dict.

        Raises:
            DomainError: 422 if any supplied field fails validation
                (invalid role, bad split sum, malformed model dict, etc.).
        """
        supplied = req.model_dump(by_alias=True, exclude_unset=True)
        patch: dict[str, Any] = {}

        for key in ("job_name", "job_description", "optimizer_name", "module_name"):
            if key in supplied and supplied[key] is not None:
                val = supplied[key]
                if not isinstance(val, str) or not val.strip():
                    raise DomainError("wizard.field_non_empty_string", status=422, field=key)
                patch[key] = val.strip()

        if "job_type" in supplied and supplied["job_type"] is not None:
            patch["job_type"] = supplied["job_type"]

        if "column_roles" in supplied and supplied["column_roles"] is not None:
            roles = supplied["column_roles"]
            if not isinstance(roles, dict):
                raise DomainError("wizard.column_roles_not_object", status=422)
            bad = {c: r for c, r in roles.items() if r not in _VALID_COLUMN_ROLES}
            if bad:
                raise DomainError(
                    "wizard.invalid_role_values",
                    status=422,
                    allowed=sorted(_VALID_COLUMN_ROLES),
                    bad=bad,
                )
            patch["column_roles"] = dict(roles)
            inputs = [c for c, r in roles.items() if r == "input"]
            outputs = [c for c, r in roles.items() if r == "output"]
            patch["columns_configured"] = bool(inputs) and bool(outputs)

        if "model_config" in supplied and supplied["model_config"] is not None:
            cleaned = _validate_model_dict(supplied["model_config"], "model_config")
            patch["model_config"] = cleaned
            if cleaned.get("name"):
                patch["model_configured"] = True

        if "reflection_model_config" in supplied and supplied["reflection_model_config"] is not None:
            patch["reflection_model_config"] = _validate_model_dict(
                supplied["reflection_model_config"], "reflection_model_config"
            )

        for list_key in ("generation_models", "reflection_models"):
            if list_key in supplied and supplied[list_key] is not None:
                items = supplied[list_key]
                if not isinstance(items, list):
                    raise DomainError("wizard.field_must_be_list", status=422, field=list_key)
                patch[list_key] = [_validate_model_dict(m, f"{list_key}[{i}]") for i, m in enumerate(items)]

        for bool_key in (
            "use_all_generation_models",
            "use_all_reflection_models",
            "shuffle",
        ):
            if bool_key in supplied and supplied[bool_key] is not None:
                patch[bool_key] = bool(supplied[bool_key])

        if "split_fractions" in supplied and supplied["split_fractions"] is not None:
            sf = supplied["split_fractions"]
            if not isinstance(sf, dict):
                raise DomainError("wizard.split_fractions_not_object", status=422)
            try:
                train = float(sf.get("train", 0.7))
                val = float(sf.get("val", 0.15))
                test = float(sf.get("test", 0.15))
            except (TypeError, ValueError) as exc:
                raise DomainError("wizard.split_fractions_not_number", status=422, error=str(exc)) from exc
            if any(v < 0 for v in (train, val, test)):
                raise DomainError("wizard.split_fractions_negative", status=422)
            total = train + val + test
            if abs(total - 1.0) > 1e-6:
                raise DomainError("wizard.split_fractions_sum", status=422, total=f"{total:.4f}")
            patch["split_fractions"] = {"train": train, "val": val, "test": test}

        if "split_mode" in supplied and supplied["split_mode"] is not None:
            patch["split_mode"] = supplied["split_mode"]

        if "seed" in supplied and supplied["seed"] is not None:
            patch["seed"] = int(supplied["seed"])

        if "optimizer_kwargs" in supplied and supplied["optimizer_kwargs"] is not None:
            ok = supplied["optimizer_kwargs"]
            if not isinstance(ok, dict):
                raise DomainError("wizard.optimizer_kwargs_not_object", status=422)
            patch["optimizer_kwargs"] = dict(ok)

        if "signature_code" in supplied and supplied["signature_code"] is not None:
            patch["signature_code"] = str(supplied["signature_code"])

        if "metric_code" in supplied and supplied["metric_code"] is not None:
            patch["metric_code"] = str(supplied["metric_code"])

        return WizardUpdateResponse(wizard_state=patch)

    return router
