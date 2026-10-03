"""AgentCore Memory: long-term review lessons, extracted and consolidated by AWS.

Each approved lesson is written as an event under an actor named after the
finding pattern, so the semantic strategy keeps lessons for one kind of finding
together. Retrieval searches only that actor's namespace. Only static error
categories leave this module; lesson text and SDK payloads are never logged.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.providers.aws.adapters import _AWSProvider, _setting
from app.providers.interfaces import ProviderError

MAX_LESSON_CHARS = 500


def actor_id(pattern: str) -> str:
    """Patterns can contain field labels with spaces; AgentCore IDs cannot."""
    return re.sub(r"[^A-Za-z0-9_/:-]", "-", pattern)


class AgentCoreLessons(_AWSProvider):
    def add(self, pattern: str, case_id: str, text: str) -> None:
        try:
            self._client("bedrock-agentcore").create_event(
                memoryId=_setting(self.settings, "agentcore_memory_id"),
                actorId=actor_id(pattern),
                sessionId=case_id,
                eventTimestamp=datetime.now(timezone.utc),
                payload=[
                    {"conversational": {"role": "USER", "content": {"text": text}}}
                ],
            )
        except Exception:
            raise ProviderError("lesson_write_failed") from None

    def namespace(self, pattern: str) -> str:
        """Resolve the strategy's namespace template for one finding pattern."""
        template = _setting(self.settings, "agentcore_memory_namespace")
        if "{memoryStrategyId}" in template:
            template = template.replace(
                "{memoryStrategyId}",
                _setting(self.settings, "agentcore_memory_strategy_id"),
            )
        return template.replace("{actorId}", actor_id(pattern))

    def search(self, pattern: str, query: str, limit: int = 3) -> list[str]:
        try:
            namespace = self.namespace(pattern)
            response = self._client("bedrock-agentcore").retrieve_memory_records(
                memoryId=_setting(self.settings, "agentcore_memory_id"),
                namespace=namespace,
                searchCriteria={"searchQuery": query, "topK": limit},
            )
            texts = [
                record["content"]["text"].strip()[:MAX_LESSON_CHARS]
                for record in response.get("memoryRecordSummaries", [])
            ]
            return [text for text in texts if text][:limit]
        except Exception:
            raise ProviderError("lesson_read_failed") from None
