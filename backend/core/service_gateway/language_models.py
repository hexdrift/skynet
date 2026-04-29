"""DSPy language model factory.

Builds ``dspy.LM`` instances from ``ModelConfig`` while filtering out
``None`` optional fields so LiteLLM does not reject the call.
"""

import dspy

from ..exceptions import ServiceError
from ..models import ModelConfig


def build_language_model(config: ModelConfig, *, disable_cache: bool = False) -> dspy.LM:
    """Construct a DSPy language model from a ModelConfig.

    Only non-None optional fields (temperature, base_url, max_tokens, top_p) are
    forwarded to ``dspy.LM`` to avoid LiteLLM rejecting unexpected None values.
    Extra kwargs from ``config.extra`` are merged in last.

    Args:
        config: Provider-agnostic model configuration.
        disable_cache: When True, force ``cache=False`` so retries always hit
            the provider. Used for user-facing surfaces (agents, serve) where
            replaying a cached response would defeat the regenerate action.

    Returns:
        A configured ``dspy.LM`` ready for use by an optimizer.

    Raises:
        ServiceError: When ``dspy.LM`` rejects the configuration.
    """

    model_name = config.name.strip("/")
    lm_kwargs: dict[str, object] = {"model": model_name}
    if config.temperature is not None:
        lm_kwargs["temperature"] = config.temperature
    if config.base_url:
        lm_kwargs["base_url"] = config.base_url
    if config.max_tokens is not None:
        lm_kwargs["max_tokens"] = config.max_tokens
    if config.top_p is not None:
        lm_kwargs["top_p"] = config.top_p
    lm_kwargs.update(config.extra)
    if disable_cache:
        lm_kwargs["cache"] = False
    try:
        language_model = dspy.LM(**lm_kwargs)
    except ValueError as exc:
        raise ServiceError(f"Failed to build language model '{config.name}': {exc}") from exc

    return language_model
