"""Routes for code formatting and pre-submit validation.

Two POST endpoints used by the submit wizard to lint/format user-authored
DSPy signature and metric code before a job is enqueued.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ...models import ValidateCodeRequest, ValidateCodeResponse
from ...service_gateway import ServiceError
from ...service_gateway.safe_exec import (
    probe_metric_on_sample,
    validate_metric_code,
    validate_signature_code,
)
from ..response_limits import AGENT_MAX_ERROR, truncate_text


def _bounded_error(message: str) -> str:
    """Truncate an exception / traceback string to a context-safe length.

    Args:
        message: The raw error message or traceback.

    Returns:
        The truncated message, never longer than :data:`AGENT_MAX_ERROR`.
    """
    return truncate_text(message, AGENT_MAX_ERROR) or message


class FormatCodeRequest(BaseModel):
    """Request body for ``POST /format-code`` — a raw Python snippet to reformat."""

    code: str


class FormatCodeResponse(BaseModel):
    """Response body for ``POST /format-code``: reformatted code plus diff / error flags."""

    code: str
    changed: bool
    error: str | None = None


def create_code_validation_router() -> APIRouter:
    """Build the code-validation router.

    Returns:
        A configured :class:`APIRouter` exposing ``/format-code`` and ``/validate-code``.
    """
    router = APIRouter()

    @router.post(
        "/format-code",
        response_model=FormatCodeResponse,
        summary="Format user-authored Python code with ruff",
    )
    def format_code(payload: FormatCodeRequest) -> FormatCodeResponse:
        """Run ``ruff format`` on the supplied snippet.

        Never raises 5xx — any formatting error is returned in the ``error`` field.

        Args:
            payload: Request body containing the raw Python snippet.

        Returns:
            A :class:`FormatCodeResponse` with the (possibly reformatted) code,
            a ``changed`` flag, and any error message.
        """
        # ``delete=False`` keeps the file readable after the writer closes so
        # ruff can pick it up via path. ``try/finally`` guarantees cleanup on
        # every exit path — non-zero ruff exit, timeout, missing binary, etc.
        # — so a long-lived API process can't leak /tmp space.
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(payload.code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["ruff", "format", tmp_path],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return FormatCodeResponse(code=payload.code, changed=False, error=result.stderr.strip())
            formatted = Path(tmp_path).read_text()
            return FormatCodeResponse(code=formatted, changed=formatted != payload.code)
        except FileNotFoundError:
            return FormatCodeResponse(code=payload.code, changed=False, error="ruff is not installed on the server")
        except subprocess.TimeoutExpired:
            return FormatCodeResponse(code=payload.code, changed=False, error="Formatting timed out")
        except (OSError, subprocess.SubprocessError) as exc:
            return FormatCodeResponse(code=payload.code, changed=False, error=str(exc))
        finally:
            if tmp_path is not None:
                Path(tmp_path).unlink(missing_ok=True)

    @router.post(
        "/validate-code",
        response_model=ValidateCodeResponse,
        summary="Pre-submit validation for signature and metric code",
        tags=["agent"],
    )
    def validate_code(payload: ValidateCodeRequest) -> ValidateCodeResponse:
        """Parse and smoke-test DSPy signature/metric code before enqueue.

        Checks: signature parse → column-mapping consistency → metric parse →
        GEPA arity (if applicable) → live sample run. Returns ``valid=True`` only
        when ``errors`` is empty; ``warnings`` lists soft issues that don't block
        submission.

        Args:
            payload: Validation request containing signature/metric code,
                column mapping, optimizer name, and an optional sample row.

        Returns:
            A :class:`ValidateCodeResponse` with ``valid``, signature fields,
            and the populated ``errors`` and ``warnings`` lists.
        """
        errors: list[str] = []
        warnings: list[str] = []
        sig_fields: dict[str, list[str]] | None = None
        image_input_fields: list[str] = []

        if not payload.signature_code and not payload.metric_code:
            errors.append("Provide signature_code and/or metric_code to validate.")

        if payload.signature_code:
            try:
                intro = validate_signature_code(payload.signature_code)
                sig_fields = {
                    "inputs": intro.input_fields,
                    "outputs": intro.output_fields,
                }
                image_input_fields = list(intro.image_input_fields)
            except ServiceError as exc:
                errors.append(_bounded_error(str(exc)))
            # Catch-all: user code may raise arbitrary exceptions; surface as validation error.
            except Exception as exc:
                errors.append(_bounded_error(f"Signature error: {exc}"))

            if sig_fields:
                missing_inputs = set(sig_fields["inputs"]) - set(payload.column_mapping.inputs.keys())
                missing_outputs = set(sig_fields["outputs"]) - set(payload.column_mapping.outputs.keys())
                if missing_inputs:
                    errors.append(
                        f"Signature input fields not mapped to columns: {sorted(missing_inputs)}. "
                        f"Mapped input columns: {sorted(payload.column_mapping.inputs.keys())}"
                    )
                if missing_outputs:
                    errors.append(
                        f"Signature output fields not mapped to columns: {sorted(missing_outputs)}. "
                        f"Mapped output columns: {sorted(payload.column_mapping.outputs.keys())}"
                    )
                extra_inputs = set(payload.column_mapping.inputs.keys()) - set(sig_fields["inputs"])
                extra_outputs = set(payload.column_mapping.outputs.keys()) - set(sig_fields["outputs"])
                if extra_inputs:
                    warnings.append(f"Input columns not in Signature (will be ignored): {sorted(extra_inputs)}")
                if extra_outputs:
                    warnings.append(f"Output columns not in Signature (will be ignored): {sorted(extra_outputs)}")

        metric_ok = False
        metric_errors_before = len(errors)
        if payload.metric_code:
            try:
                metric_info = validate_metric_code(payload.metric_code)
                metric_ok = True
            except ServiceError as exc:
                errors.append(_bounded_error(str(exc)))
            # Catch-all: user code may raise arbitrary exceptions; surface as validation error.
            except Exception as exc:
                errors.append(_bounded_error(f"Metric error: {exc}"))

            if metric_ok and payload.optimizer_name == "gepa":
                param_names = metric_info.param_names
                if len(param_names) < 5:
                    errors.append(
                        f"GEPA metric must accept 5 arguments: (gold, pred, trace, pred_name, pred_trace). "
                        f"Found {len(param_names)}: ({', '.join(param_names)}). "
                        f"See https://dspy.ai/api/optimizers/GEPA for details."
                    )

            metric_has_errors = len(errors) > metric_errors_before
            if metric_ok and payload.sample_row and not metric_has_errors:
                mapping = payload.column_mapping
                ex_data: dict = {}
                for sig_field, col_name in mapping.inputs.items():
                    ex_data[sig_field] = payload.sample_row.get(col_name, "")
                for sig_field, col_name in mapping.outputs.items():
                    ex_data[sig_field] = payload.sample_row.get(col_name, "")
                try:
                    probe = probe_metric_on_sample(
                        metric_code=payload.metric_code,
                        example_payload=ex_data,
                        prediction_payload=ex_data,
                        input_field_names=list(mapping.inputs.keys()),
                        image_input_fields=image_input_fields,
                    )
                except ServiceError as exc:
                    errors.append(_bounded_error(str(exc)))
                except Exception as exc:  # Catch-all: subprocess / dspy setup failure.
                    errors.append(_bounded_error(f"Error running metric on sample row: {exc}"))
                else:
                    is_gepa = payload.optimizer_name == "gepa"
                    if probe.error is not None:
                        errors.append(_bounded_error(f"Error running metric on sample row: {probe.error}"))
                    elif probe.result_kind == "none":
                        errors.append(
                            "Metric returned None. "
                            + (
                                "GEPA requires dspy.Prediction with score and feedback fields."
                                if is_gepa
                                else "Expected a numeric (float) or boolean return value."
                            )
                        )
                    elif probe.result_kind == "prediction":
                        if not is_gepa:
                            errors.append(
                                "Metric returns dspy.Prediction but the selected optimizer "
                                "requires a numeric (float/bool) return value."
                            )
                    elif probe.result_kind == "numeric":
                        if is_gepa:
                            errors.append(
                                "GEPA requires the metric to return dspy.Prediction(score=..., feedback=...), "
                                "not a numeric value."
                            )
                    else:
                        errors.append(
                            f"Metric returned {probe.result_type_name}. "
                            + (
                                "GEPA requires dspy.Prediction with score and feedback fields."
                                if is_gepa
                                else "Expected a numeric (float) or boolean return value."
                            )
                        )

        return ValidateCodeResponse(
            valid=len(errors) == 0,
            signature_fields=sig_fields,
            errors=errors,
            warnings=warnings,
        )

    return router
