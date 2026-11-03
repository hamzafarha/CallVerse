"""The LLM layer: OpenRouter (hosted models) first, local Hugging Face models as backup.

Pinned models, a disk cache of answers, a trace of every call, and live streaming.
When no model can answer, the agents use their offline templates.
"""

# This file re-exports the main names, so other code can simply write `from callverse.llm import LLMClient,
# get_llm`.
from callverse.llm.cache import LLMCache, cache_key
from callverse.llm.client import (
    LLMClient,
    LLMResponse,
    LLMSettings,
    LLMUnavailableError,
    get_llm,
    load_llm_settings,
    set_llm,
)
from callverse.llm.tracing import Tracer

__all__ = [
    "LLMCache",
    "LLMClient",
    "LLMResponse",
    "LLMSettings",
    "LLMUnavailableError",
    "Tracer",
    "cache_key",
    "get_llm",
    "load_llm_settings",
    "set_llm",
]
