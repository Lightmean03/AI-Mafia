"""LLM provider/config and model construction for AI Mafia."""

import os
from typing import Any

# Type alias for model passed to Agent.run(); pydantic-ai accepts Model | str | None
ModelT = Any

# Default env var names
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
ENV_GOOGLE_API_KEY = "GOOGLE_GENERATIVE_AI_API_KEY"
ENV_XAI_API_KEY = "XAI_API_KEY"
ENV_OLLAMA_BASE_URL = "OLLAMA_BASE_URL"
ENV_OLLAMA_API_KEY = "OLLAMA_API_KEY"
ENV_DEFAULT_PROVIDER = "DEFAULT_PROVIDER"
ENV_DEFAULT_MODEL = "DEFAULT_MODEL"


def get_model_from_config(
    provider: str,
    model_name: str,
    api_key: str | None = None,
) -> ModelT:
    """
    Build a pydantic-ai Model instance for the given provider/model/api_key.
    If api_key is None, falls back to env (OPENAI_API_KEY, etc.).
    """
    key = api_key or _env_key_for_provider(provider)
    model_name = model_name or _default_model_for_provider(provider)

    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(api_key=key) if key else OpenAIProvider(),
        )
    if provider == "anthropic":
        try:
            from pydantic_ai.models.anthropic import AnthropicChatModel
            from pydantic_ai.providers.anthropic import AnthropicProvider
            return AnthropicChatModel(
                model_name,
                provider=AnthropicProvider(api_key=key) if key else AnthropicProvider(),
            )
        except ImportError:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
            return OpenAIChatModel(
                model_name,
                provider=OpenAIProvider(
                    base_url="https://api.anthropic.com/v1",
                    api_key=key,
                ) if key else OpenAIProvider(),
            )
    if provider in ("google", "gemini"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return OpenAIChatModel(
            model_name or "gemini-2.0-flash",
            provider=OpenAIProvider(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=key,
            ) if key else OpenAIProvider(),
        )
    if provider == "ollama":
        # Local Ollama: OLLAMA_BASE_URL (default http://localhost:11434/v1), no API key
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        base_url = os.environ.get(ENV_OLLAMA_BASE_URL, "http://localhost:11434/v1")
        return OpenAIChatModel(
            model_name or "llama3.2",
            provider=OpenAIProvider(base_url=base_url, api_key=api_key or "ollama"),
        )
    if provider == "ollama_cloud":
        # Ollama Cloud (ollama.com): OLLAMA_API_KEY, https://ollama.com/v1
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return OpenAIChatModel(
            model_name or "llama3.2",
            provider=OpenAIProvider(
                base_url="https://ollama.com/v1",
                api_key=key,
            ) if key else OpenAIProvider(base_url="https://ollama.com/v1", api_key=""),
        )
    if provider == "grok":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return OpenAIChatModel(
            model_name or "grok-2",
            provider=OpenAIProvider(base_url="https://api.x.ai/v1", api_key=key) if key else OpenAIProvider(base_url="https://api.x.ai/v1", api_key=""),
        )
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    return OpenAIChatModel(
        model_name or "gpt-4o-mini",
        provider=OpenAIProvider(api_key=key) if key else OpenAIProvider(),
    )


def _env_key_for_provider(provider: str) -> str | None:
    key = os.environ.get(ENV_OPENAI_API_KEY)
    if provider == "anthropic":
        key = os.environ.get(ENV_ANTHROPIC_API_KEY)
    elif provider in ("google", "gemini"):
        key = os.environ.get(ENV_GOOGLE_API_KEY)
    elif provider == "grok":
        key = os.environ.get(ENV_XAI_API_KEY)
    elif provider == "ollama":
        return None  # Local only; no key
    elif provider == "ollama_cloud":
        return os.environ.get(ENV_OLLAMA_API_KEY)
    return key or os.environ.get(ENV_OPENAI_API_KEY)


def _default_model_for_provider(provider: str) -> str:
    return os.environ.get(ENV_DEFAULT_MODEL) or {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "google": "gemini-2.0-flash",
        "gemini": "gemini-2.0-flash",
        "ollama": "llama3.2",
        "ollama_cloud": "llama3.2",
        "grok": "grok-2",
    }.get(provider, "gpt-4o-mini")
