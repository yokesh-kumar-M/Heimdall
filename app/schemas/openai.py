from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """A single message in an OpenAI-style chat completion request.

    Uses extra='allow' so newer fields (tool_calls, name, etc.) pass through
    untouched to the upstream provider.
    """

    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool", "developer"]
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request.

    Intentionally loose: only `model` and `messages` are required. All other
    OpenAI parameters (temperature, tools, response_format, stream, etc.)
    are accepted via extra='allow' and forwarded as-is.
    """

    model_config = ConfigDict(extra="allow")

    model: str = Field(..., description="Upstream model identifier.")
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = False
