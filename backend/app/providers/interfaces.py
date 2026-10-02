"""Provider ports: no HTTP, Lambda or SDK dependencies in business logic."""

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol


class ProviderError(Exception):
    """A safe category, never a provider payload or document content."""


class UnsupportedDocument(ProviderError):
    pass


@dataclass
class TextLine:
    text: str
    confidence: float = 1.0
    bounding_box: dict[str, float] | None = None


@dataclass
class Extraction:
    lines: list[TextLine]
    page_count: int = 1


@dataclass
class PrivacyResult:
    status: Literal["unchanged", "masked", "blocked", "error"]
    text: str = ""


class DocumentExtractor(Protocol):
    def extract(self, content: bytes) -> Extraction: ...


class PrivacyFilter(Protocol):
    def filter(
        self, text: str, direction: Literal["INPUT", "OUTPUT"]
    ) -> PrivacyResult: ...


class ExplanationGenerator(Protocol):
    def explain(self, sanitized_json: str) -> str: ...


class DocumentStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def presign_upload(self, key: str) -> dict[str, Any]: ...
    def confirm_upload(self, key: str) -> int: ...


class CaseStorage(Protocol):
    def create(self, record: dict[str, Any]) -> None: ...
    def get(self, case_id: str) -> dict[str, Any] | None: ...
    def update(
        self, case_id: str, mutate: Callable[[dict[str, Any]], None]
    ) -> dict[str, Any]: ...
    def interrupt_pending(self) -> None: ...
    def claim_run(self, case_id: str, run_id: str, owner: str, lease_seconds: int) -> bool: ...
    def renew_run(self, case_id: str, run_id: str, owner: str, lease_seconds: int) -> bool: ...
    def finish_run(self, case_id: str, run_id: str, owner: str, result: dict[str, Any]) -> bool: ...


class JobDispatcher(Protocol):
    def dispatch(self, case_id: str, run_id: str) -> None: ...
    def close(self) -> None: ...


@dataclass
class Providers:
    extraction: DocumentExtractor
    privacy: PrivacyFilter
    explanations: ExplanationGenerator
    documents: DocumentStorage
    cases: CaseStorage
    dispatcher: JobDispatcher | None = field(default=None)
