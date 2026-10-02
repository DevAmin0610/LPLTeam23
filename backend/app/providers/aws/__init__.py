"""Lazy AWS provider adapters; importing this package never contacts AWS."""

from .adapters import (
    BedrockExplanationGenerator,
    DynamoCaseStorage,
    GuardrailPrivacyFilter,
    LambdaJobDispatcher,
    S3DocumentStorage,
    TextractExtractor,
)

__all__ = [
    "TextractExtractor",
    "GuardrailPrivacyFilter",
    "BedrockExplanationGenerator",
    "S3DocumentStorage",
    "DynamoCaseStorage",
    "LambdaJobDispatcher",
]
