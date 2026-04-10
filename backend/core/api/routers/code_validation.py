"""Routes for code formatting and pre-submit validation.

Two POST endpoints used by the submit wizard to lint/format user-authored
DSPy signature and metric code before a job is enqueued.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ...models import ValidateCodeRequest, ValidateCodeResponse
from ...service_gateway import ServiceError


class FormatCodeRequest(BaseModel):
    code: str


class FormatCodeResponse(BaseModel):
    code: str
    changed: bool
    error: Optional[str] = None


def create_code_validation_router() -> APIRouter:
    """Build the code-validation router.

    Returns:
        APIRouter: Router with ``POST /format-code`` and ``POST /validate-code``.
    """
    router = APIRouter()

    @router.post("/format-code", response_model=FormatCodeResponse)
    def format_code(payload: FormatCodeRequest) -> FormatCodeResponse:
        """Format Python code using ruff."""
        import os
        import subprocess
        import tempfile

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(payload.code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["ruff", "format", tmp_path],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return FormatCodeResponse(code=payload.code, changed=False, error=result.stderr.strip())
            with open(tmp_path, "r") as f:
                formatted = f.read()
            os.unlink(tmp_path)
            return FormatCodeResponse(code=formatted, changed=formatted != payload.code)
        except FileNotFoundError:
            return FormatCodeResponse(code=payload.code, changed=False, error="ruff is not installed on the server")
        except subprocess.TimeoutExpired:
            return FormatCodeResponse(code=payload.code, changed=False, error="Formatting timed out")
        except Exception as exc:
            return FormatCodeResponse(code=payload.code, changed=False, error=str(exc))

    @router.post("/validate-code", response_model=ValidateCodeResponse)
    def validate_code(payload: ValidateCodeRequest) -> ValidateCodeResponse:
        """Validate signature and metric code before job submission.

        Parses signature code, checks field/mapping compatibility, parses
        metric code, and runs the metric on a sample row to verify it works.
        """
        from ...service_gateway.data import (
            extract_signature_fields,
            load_metric_from_code,
            load_signature_from_code,
        )
        import dspy

        errors: list[str] = []
        warnings: list[str] = []
        sig_fields: dict[str, list[str]] | None = None

        if not payload.signature_code and not payload.metric_code:
            errors.append("Provide signature_code and/or metric_code to validate.")

        # 1. Validate signature code (if provided)
        if payload.signature_code:
            try:
                signature_cls = load_signature_from_code(payload.signature_code)
                inputs, outputs = extract_signature_fields(signature_cls)
                sig_fields = {"inputs": inputs, "outputs": outputs}
            except ServiceError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"Signature error: {exc}")

            # 2. Check signature fields match column mapping
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
                    warnings.append(
                        f"Input columns not in Signature (will be ignored): {sorted(extra_inputs)}"
                    )
                if extra_outputs:
                    warnings.append(
                        f"Output columns not in Signature (will be ignored): {sorted(extra_outputs)}"
                    )

        # 3. Validate metric code (if provided)
        metric_fn = None
        metric_errors_before = len(errors)
        if payload.metric_code:
            try:
                metric_fn = load_metric_from_code(payload.metric_code)
            except ServiceError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"Metric error: {exc}")

            # 3b. GEPA metrics must accept 5 parameters: (gold, pred, trace, pred_name, pred_trace)
            if metric_fn and payload.optimizer_name == "gepa":
                import inspect
                sig = inspect.signature(metric_fn)
                params = list(sig.parameters.values())
                if len(params) < 5:
                    param_names = [p.name for p in params]
                    errors.append(
                        f"GEPA metric must accept 5 arguments: (gold, pred, trace, pred_name, pred_trace). "
                        f"Found {len(params)}: ({', '.join(param_names)}). "
                        f"See https://dspy.ai/api/optimizers/GEPA for details."
                    )

            # 4. Run the metric on a sample (uses mapping keys, doesn't require signature)
            metric_has_errors = len(errors) > metric_errors_before
            if metric_fn and payload.sample_row and not metric_has_errors:
                try:
                    mapping = payload.column_mapping
                    ex_data: dict = {}
                    for sig_field, col_name in mapping.inputs.items():
                        ex_data[sig_field] = payload.sample_row.get(col_name, "")
                    for sig_field, col_name in mapping.outputs.items():
                        ex_data[sig_field] = payload.sample_row.get(col_name, "")
                    example = dspy.Example(**ex_data).with_inputs(*mapping.inputs.keys())
                    pred = dspy.Prediction(**ex_data)

                    result = metric_fn(example, pred, trace=None)
                    is_gepa = payload.optimizer_name == "gepa"
                    if result is None:
                        errors.append(
                            "Metric returned None. "
                            + ("GEPA requires dspy.Prediction with score and feedback fields." if is_gepa
                               else "Expected a numeric (float) or boolean return value.")
                        )
                    elif isinstance(result, dspy.Prediction) and hasattr(result, "score"):
                        if not is_gepa:
                            errors.append(
                                "Metric returns dspy.Prediction but the selected optimizer requires a numeric (float/bool) return value."
                            )
                    elif isinstance(result, (int, float, bool)):
                        if is_gepa:
                            errors.append(
                                "GEPA requires the metric to return dspy.Prediction(score=..., feedback=...), "
                                "not a numeric value."
                            )
                    else:
                        errors.append(
                            f"Metric returned {type(result).__name__}. "
                            + ("GEPA requires dspy.Prediction with score and feedback fields." if is_gepa
                               else "Expected a numeric (float) or boolean return value.")
                        )
                except Exception as exc:
                    errors.append(f"Error running metric on sample row: {exc}")

        return ValidateCodeResponse(
            valid=len(errors) == 0,
            signature_fields=sig_fields,
            errors=errors,
            warnings=warnings,
        )

    return router
