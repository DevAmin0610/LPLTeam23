"""Demonstration only: masks supported synthetic IDs, not general-purpose PII."""

import json
import re
from app.providers.interfaces import PrivacyResult


def mask(text: str) -> str:
    text = re.sub(r"(?<!\d)\d{3}[ -]?\d{2}[ -]?\d{4}(?!\d)", "[SSN MASKED]", text)
    text = re.sub(r"\b(?:DEMO|RECV)-[A-Z0-9-]+\b", "[ACCOUNT MASKED]", text, flags=re.I)
    return text


class LocalPrivacyFilter:
    def filter(self, text: str, direction: str) -> PrivacyResult:
        sanitized = mask(text)
        return PrivacyResult("masked" if sanitized != text else "unchanged", sanitized)


class TemplateExplanations:
    def explain(self, sanitized_json: str) -> str:
        payload = json.loads(sanitized_json)
        text = payload["explanation"]
        lessons = payload.get("approved_lessons")
        if lessons:
            text += f" Review memory: {lessons[0]}"
        return text + " This is a sample-rule result; advisor review is required."
