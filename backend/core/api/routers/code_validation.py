"""Routes for code formatting and pre-submit validation.

Two POST endpoints used by the submit wizard to lint/format user-authored
DSPy signature and metric code before a job is enqueued.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...models import ValidateCodeRequest, ValidateCodeResponse
from ...service_gateway import ServiceError


class FormatCodeRequest(BaseModel):
    code: str


class FormatCodeResponse(BaseModel):
    code: str
    changed: bool
    error: str | None = None


def create_code_validation_router() -> APIRouter:
    """Build the code-validation router.

    Returns:
        APIRouter: Router with ``POST /format-code`` and ``POST /validate-code``.
    """
    router = APIRouter()

    @router.post(
        "/format-code",
        response_model=FormatCodeResponse,
        summary="Format user-authored Python code with ruff",
    )
    def format_code(payload: FormatCodeRequest) -> FormatCodeResponse:
        """Run ``ruff format`` against the supplied code snippet.

        Used by the submit wizard's code editor to auto-format signature
        and metric code on demand. The input is written to a tempfile,
        formatted, read back, and deleted — no state is persisted. This
        endpoint never raises 5xx for user input errors: a malformed
        snippet is returned with ``error`` set and the original ``code``
        intact. A five-second timeout protects the server from
        pathological input.

        Args:
            payload: Request body containing the ``code`` field to
                format.

        Returns:
            ``FormatCodeResponse`` with fields ``code`` (the formatted
            source, or original on failure), ``changed`` (whether
            formatting produced any difference) and ``error`` (a human
            readable failure reason such as ruff missing, timeout or
            syntax error, or ``None`` on success).
        """
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
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return FormatCodeResponse(code=payload.code, changed=False, error=result.stderr.strip())
            with open(tmp_path) as f:
                formatted = f.read()
            os.unlink(tmp_path)
            return FormatCodeResponse(code=formatted, changed=formatted != payload.code)
        except FileNotFoundError:
            return FormatCodeResponse(code=payload.code, changed=False, error="ruff is not installed on the server")
        except subprocess.TimeoutExpired:
            return FormatCodeResponse(code=payload.code, changed=False, error="Formatting timed out")
        except Exception as exc:
            return FormatCodeResponse(code=payload.code, changed=False, error=str(exc))

    @router.post(
        "/validate-code",
        response_model=ValidateCodeResponse,
        summary="Pre-submit validation for signature and metric code",
    )
    def validate_code(payload: ValidateCodeRequest) -> ValidateCodeResponse:
        """Parse and smoke-test DSPy signature/metric code before enqueue.

        Catching errors here — instead of inside the worker — saves
        users a round-trip and keeps the queue clean of jobs that can
        never succeed. Accepts either ``signature_code``,
        ``metric_code``, or both; passing neither is itself an error.

        Checks performed (in order):
            1. **Signature parse**: compile ``signature_code`` into a
               ``dspy.Signature`` subclass and extract its declared
               input/output field names.
            2. **Column mapping consistency**: verify every signature
               field is mapped to a dataset column. Unmapped fields
               become errors; extra mapped columns that don't exist in
               the signature become warnings.
            3. **Metric parse**: compile ``metric_code`` and locate a
               callable suitable for the declared optimizer.
            4. **GEPA arity check**: if the selected optimizer is GEPA,
               the metric signature must accept five parameters
               ``(gold, pred, trace, pred_name, pred_trace)``.
            5. **Live sample run**: invoke the metric on a synthetic
               ``dspy.Example`` built from ``sample_row`` and verify the
               return type matches what the chosen optimizer expects.

        Args:
            payload: Request body with optional ``signature_code`` and
                ``metric_code``, the active ``column_mapping``, the
                ``optimizer_name`` (needed for GEPA arity checks) and
                an optional ``sample_row`` used by the live smoke test.

        Returns:
            ``ValidateCodeResponse`` with ``valid`` (``True`` only when
            ``errors`` is empty), ``signature_fields`` populated
            whenever signature parsing succeeds, ``errors`` listing
            hard failures that block submission, and ``warnings``
            listing soft issues that don't block submission.
        """
        import dspy

        from ...service_gateway.data import (
            extract_signature_fields,
            load_metric_from_code,
            load_signature_from_code,
        )

        errors: list[str] = []
        warnings: list[str] = []
        sig_fields: dict[str, list[str]] | None = None

        if not payload.signature_code and not payload.metric_code:
            errors.append("Provide signature_code and/or metric_code to validate.")

        if payload.signature_code:
            try:
                signature_cls = load_signature_from_code(payload.signature_code)
                inputs, outputs = extract_signature_fields(signature_cls)
                sig_fields = {"inputs": inputs, "outputs": outputs}
            except ServiceError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"Signature error: {exc}")

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

        metric_fn = None
        metric_errors_before = len(errors)
        if payload.metric_code:
            try:
                metric_fn = load_metric_from_code(payload.metric_code)
            except ServiceError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"Metric error: {exc}")

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
                            + (
                                "GEPA requires dspy.Prediction with score and feedback fields."
                                if is_gepa
                                else "Expected a numeric (float) or boolean return value."
                            )
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
                            + (
                                "GEPA requires dspy.Prediction with score and feedback fields."
                                if is_gepa
                                else "Expected a numeric (float) or boolean return value."
                            )
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
