"""Interface for Part 3's extraction pipeline.

Nothing in this file calls a real API. You implement a real client against
the LLM provider of your choice (OpenAI, Anthropic, or equivalent) for the
actual pipeline. FakeLLMClient below is provided only so your own unit tests
don't need a real API key or network access.
"""

from typing import Protocol, TypedDict


class ExtractedAttribute(TypedDict):
    kind: str  # need | offer | context | interest
    text: str
    confidence: float
    restricted: bool


class LLMClient(Protocol):
    def extract_attributes(self, message_text: str) -> list[ExtractedAttribute]:
        """Extract structured attributes from one raw member message."""
        ...


class FakeLLMClient:
    """Trivial test double — does not call any real API."""

    def __init__(self, canned_response: list[ExtractedAttribute] | None = None) -> None:
        self.canned_response = canned_response or []
        self.calls: list[str] = []

    def extract_attributes(self, message_text: str) -> list[ExtractedAttribute]:
        self.calls.append(message_text)
        return self.canned_response
