"""Tests for the OpenAI-compatible recommendation embedding client."""

from __future__ import annotations

from unittest.mock import Mock, patch

from pydantic import SecretStr

from ..recommendations import embeddings


def test_embedding_api_client_normalizes_openai_response() -> None:
    """The client truncates and normalizes the first returned embedding."""
    with (
        patch.object(embeddings.settings, "recommendations_embedding_base_url", "https://llm.internal/v1"),
        patch.object(embeddings.settings, "recommendations_embedding_model", "embed-model"),
        patch.object(embeddings.settings, "recommendations_embedding_dim", 2),
        patch.object(embeddings.settings, "recommendations_embedding_api_key", SecretStr("embed-secret")),
        patch.object(embeddings.settings, "openai_api_key", None),
        patch.object(embeddings.requests, "post") as post,
    ):
        response = Mock()
        response.json.return_value = {"data": [{"embedding": [3.0, 4.0, 99.0]}]}
        post.return_value = response

        client = embeddings._EmbeddingApiClient()
        vector = client.encode("hello")

    assert vector == [0.6, 0.8]
    post.assert_called_once_with(
        "https://llm.internal/v1/embeddings",
        headers={"Content-Type": "application/json", "Authorization": "Bearer embed-secret"},
        json={"model": "embed-model", "input": "hello"},
        timeout=embeddings.settings.default_timeout,
    )
    response.raise_for_status.assert_called_once_with()


def test_embedding_api_client_requires_configured_base_url() -> None:
    """An unconfigured API degrades to unavailable recommendations."""
    with (
        patch.object(embeddings.settings, "recommendations_embedding_base_url", ""),
        patch.object(embeddings.settings, "recommendations_embedding_model", "embed-model"),
    ):
        client = embeddings._EmbeddingApiClient()

    assert client.available() is False
    assert client.encode("hello") is None


def test_embedding_api_client_rejects_short_vectors() -> None:
    """Vectors shorter than the pgvector schema dimension are ignored."""
    with (
        patch.object(embeddings.settings, "recommendations_embedding_base_url", "https://llm.internal/v1"),
        patch.object(embeddings.settings, "recommendations_embedding_model", "embed-model"),
        patch.object(embeddings.settings, "recommendations_embedding_dim", 3),
        patch.object(embeddings.requests, "post") as post,
    ):
        response = Mock()
        response.json.return_value = {"data": [{"embedding": [1.0, 0.0]}]}
        post.return_value = response

        client = embeddings._EmbeddingApiClient()

    assert client.encode("hello") is None
