"""English message templates for backend error envelopes (Phase 2 of PER-83).

The canonical user-facing copy lives in ``i18n/locales/he.json`` and is rendered
on the frontend via the ``code`` + ``params`` pair carried on every error
response. The backend, however, still needs a human-readable ``detail`` string
for API consumers without an i18n layer (curl, server logs, OpenAPI examples,
3rd-party clients). These English templates provide that.

Keys mirror :class:`core.i18n_keys.I18nKey` exactly. Placeholders use the same
``{name}`` slots as the Hebrew templates so callers can pass identical params
without translation. ``{term.X}`` references in the Hebrew templates are
flattened here to plain English nouns since the API consumer does not need the
shared term layer.

This module is intentionally a flat literal — no codegen, no I/O, no lookups —
so missing-key drift surfaces immediately at import time.
"""

from __future__ import annotations

ENGLISH_MESSAGES: dict[str, str] = {
    "agent.approval.unknown_call_id": "No pending approval for the given call_id.",
    "agent.status.tool_end": "Tool finished.",
    "agent.status.tool_start": "Agent invoking tool…",
    "admin.forbidden": "Admin privileges are required for this operation.",
    "admin.invalid_username": "Username must not be blank.",
    "admin.quota_save_failed": "Failed to save quota override.",
    "analytics.other_bucket": "Other",
    "auth.invalid_token": "Authentication token is invalid or expired.",
    "auth.missing_token": "Authentication token is required.",
    "auth.not_configured": "Backend authentication is not configured.",
    "code_agent.upstream_failed": "Code agent failed: {error}",
    "dataset.column_roles_invalid": "Invalid role values (must be 'input', 'output', or 'ignore'): {bad}",
    "dataset.column_roles_need_input": "At least one column must have role 'input'.",
    "dataset.column_roles_need_output": "At least one column must have role 'output'.",
    "dataset.column_roles_unknown": "column_roles references columns not present in dataset_columns: {unknown}",
    "dataset.profile.class_imbalance": "Class imbalance in '{column_name}' (ratio {ratio}:1). Add more examples for the underrepresented classes.",
    "dataset.profile.duplicates": "Detected {duplicate_count} duplicate rows by input columns. Duplicates can leak the same examples into both train and test splits.",
    "dataset.profile.empty": "Dataset must contain at least one row.",
    "dataset.profile.missing_target": "{missing} rows have a missing value in target column '{column_name}'. Remove or fill them before running.",
    "dataset.profile.rare_class": "Column '{column_name}' contains rare classes ({rare_classes}); some may be absent from the val/test splits.",
    "dataset.profile.too_small": "Dataset has only {row_count} examples — too few to estimate a real improvement. Add more examples for stable scores.",
    "dataset.sample_unknown": "Unknown dataset sample '{sample_id}'. Call GET /datasets/samples for the list of valid ids.",
    "dataset.split.rationale.large": "Dataset is large ({total} examples). Capped val at {val_count} and test at {test_count} examples — enough for stable scores without wasting optimization time.",
    "dataset.split.rationale.medium": "Dataset is medium-sized ({total} examples). Using a 60/20/20 split — enough examples for each of the three sets.",
    "dataset.split.rationale.small": "Dataset is small ({total} examples). Allocated 80% to train and 20% to val so GEPA gets a stable score per candidate; not enough examples for a separate test set.",
    "dataset.split.rationale.tiny": "Dataset is very small ({total} examples). Not enough for separate val/test sets — GEPA will train on all examples and reuse them as judges during optimization.",
    "filter.invalid_optimization_type": "Invalid optimization-type filter '{value}'. Allowed values: {allowed}",
    "filter.invalid_status": "Invalid status filter '{value}'. Allowed values: {allowed}",
    "grid_search.artifact_per_pair_redirect": "Grid-search runs produce per-pair artifacts. Use GET /optimizations/{optimization_id}/grid-result instead.",
    "grid_search.cancelled_no_result": "Grid search was cancelled and produced no result.",
    "grid_search.cannot_delete_pair": "Cannot delete a pair while the optimization is in state '{status}'. Cancel the optimization first.",
    "grid_search.corrupt_result": "Grid-search result data is corrupt.",
    "grid_search.failed_no_result": "Grid search failed and produced no result. Error: {error}",
    "grid_search.no_best_pair": "Grid search has no winning pair.",
    "grid_search.no_best_program_artifact": "The winning pair has no program artifact.",
    "grid_search.no_result_available": "No grid-search result available.",
    "grid_search.no_result_to_modify": "Grid search has no result to modify.",
    "grid_search.not_a_grid_search": "Optimization is not a grid search.",
    "grid_search.pair_failed_error": "Pair at position {pair_index} failed: {error}",
    "grid_search.pair_no_artifact": "Pair at position {pair_index} has no program artifact.",
    "grid_search.pair_position_missing": "No pair at position {pair_index} in the grid-search result.",
    "grid_search.pair_submission_grid_only": "Pair-scoped submission is only available for grid-search runs.",
    "grid_search.pair_test_results_grid_only": "Pair-scoped test results are only available for grid-search runs.",
    "health.workers_dead": "Worker threads are not running.",
    "health.workers_stuck": "Worker threads have been stuck for {seconds} seconds.",
    "notifier.label.error": "error",
    "notifier.label.model": "model",
    "notifier.label.module": "module",
    "notifier.label.optimizer": "optimizer",
    "notifier.label.score": "score",
    "notifier.label.type": "type",
    "notifier.label.user": "user",
    "notifier.link.details": "Optimization details",
    "notifier.link.follow": "Follow optimization",
    "notifier.link.results": "View results",
    "notifier.title.cancelled": "Optimization cancelled",
    "notifier.title.completed": "Optimization completed successfully",
    "notifier.title.failed": "Optimization failed",
    "notifier.title.new": "New optimization",
    "optimization.already_terminal": "Optimization is already in terminal state '{status}'.",
    "optimization.cancelled_no_artifact": "Optimization was cancelled and produced no artifact.",
    "optimization.cannot_delete": "Cannot delete an optimization in state '{status}'. Cancel it first.",
    "optimization.cannot_resubmit_payload": "Cannot resubmit the saved payload: {error}",
    "optimization.clone_no_payload": "Source optimization has no saved payload to clone.",
    "optimization.corrupt_column_mapping": "Saved column mapping is invalid.",
    "optimization.corrupt_result": "Optimization result data is corrupt.",
    "optimization.dataset_unavailable": "Optimization's dataset is unavailable.",
    "optimization.failed_no_artifact": "Optimization failed and produced no artifact. Error: {error}",
    "optimization.no_artifact_generic": "Optimization produced no artifact.",
    "optimization.no_metric_code": "Optimization has no metric code.",
    "optimization.no_model_config": "No model config found.",
    "optimization.no_payload": "Optimization has no payload.",
    "optimization.no_program_artifact": "No program artifact.",
    "optimization.no_program_artifact_scoped": "Optimization has no program artifact.",
    "optimization.no_result": "Optimization has no result data.",
    "optimization.no_result_for_artifact": "Optimization has no result.",
    "optimization.no_result_pending": "Optimization has no result yet.",
    "optimization.not_finished": "Optimization is not finished.",
    "optimization.not_found": "Optimization not found: '{optimization_id}'.",
    "optimization.not_success_status_for_serve": "Optimization is in state '{status}' — only successfully completed optimizations can be served.",
    "optimization.not_success_status_for_test_results": "Optimization is in state '{status}' — only successfully completed optimizations have test results.",
    "optimization.pairs_label": "{count} pairs",
    "optimization.payload_unavailable": "Optimization payload is unavailable.",
    "optimization.retry_no_payload": "Source optimization has no saved payload to retry.",
    "optimization.retry_wrong_status": "Only optimizations in 'failed' or 'cancelled' state can be retried — this one is in '{status}'. Clone it instead.",
    "quota.reached": "Per-user limit of {quota} optimizations reached. Delete old optimizations to create new ones.",
    "serve.missing_inputs": "Missing required input fields: {missing}. Expected: {input_fields}",
    "serve.no_declared_inputs": "Artifact has no declared input fields; cannot safely validate inputs.",
    "serve.no_model_config": "No model config found for the run. Provide model_config_override.",
    "submission.module_resolve_failed": "Module load failed: {error}",
    "submission.validation_failed": "Payload validation failed: {error}",
    "submission.vision_required": "Dataset contains image columns ({fields}) but the selected model ('{model}') does not support image inputs. Pick a vision-capable model.",
    "submit.no_models_available": "No models available in the catalog — configure a provider API key first.",
    "template.cannot_delete_others": "You can only delete your own templates.",
    "template.cannot_update_others": "You can only update your own templates.",
    "template.not_found": "Template not found.",
    "template.update_requires_field": "Provide at least one of 'name', 'description', or 'config' to update.",
    "wizard.column_roles_not_object": "column_roles must be an object.",
    "wizard.field_must_be_list": "{field} must be a list.",
    "wizard.field_non_empty_string": "{field} must be a non-empty string.",
    "wizard.invalid_role_values": "Invalid role values (must be one of {allowed}): {bad}",
    "wizard.model_base_url_not_string": "{field}.base_url must be a string.",
    "wizard.model_extra_not_object": "{field}.extra must be an object.",
    "wizard.model_max_tokens_int": "{field}.max_tokens must be an integer.",
    "wizard.model_name_non_empty_string": "{field}.name must be a non-empty string.",
    "wizard.model_not_json_object": "{field} must be a JSON object.",
    "wizard.model_number_required": "{field}.{key} must be a number.",
    "wizard.optimizer_kwargs_not_object": "optimizer_kwargs must be an object.",
    "wizard.split_fractions_negative": "split_fractions must be non-negative.",
    "wizard.split_fractions_not_number": "split_fractions values must be numbers: {error}",
    "wizard.split_fractions_not_object": "split_fractions must be an object with train/val/test keys.",
    "wizard.split_fractions_sum": "split_fractions must sum to 1.0, got {total}",
}


def t_en(key: str, /, **params: object) -> str:
    """Render an English template by stable semantic key.

    Mirrors the ``str.format`` contract of :func:`core.i18n.t` so a caller can
    swap one for the other without touching params. Returns the key itself when
    no template exists, surfacing drift as an obvious development artifact.

    Args:
        key: Catalog identifier for the message template.
        **params: Optional placeholder values substituted via ``str.format``.

    Returns:
        The rendered English string (or ``key`` when no template exists).
    """
    template = ENGLISH_MESSAGES.get(key, key)
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template
