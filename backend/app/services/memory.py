"""Review memory: remember APPROVED reviewer decisions for each KIND of finding.

The memory is keyed by privacy-safe patterns (see rules.PATTERN_LABELS), and
holds one approved decision per case per pattern: {pattern: {"cases": {case_id: status},
"updated_at": iso}}. No field values, names, identifiers or reviewer notes are
stored. A decision becomes a lesson only when the reviewer explicitly marks it
"remember". History is advisory: it adds context to a finding and never changes
or dismisses it.
"""

from __future__ import annotations

from typing import Any

from app.services.rules import pattern_label

MAX_CASES_PER_PATTERN = 200
LEAN = 0.75  # Share of past decisions needed before a hint is shown.
MIN_FOR_PATTERN = 2  # Fewer past decisions are reported, not called a pattern.


def record(
    data: dict[str, Any], pattern: str, case_id: str, status: str, when: str
) -> None:
    patterns = data.setdefault("patterns", {})
    entry = patterns.setdefault(pattern, {"cases": {}, "updated_at": when})
    cases = entry["cases"]
    # Re-deciding a finding replaces this case's previous decision, so toggling
    # accept/dismiss never double-counts. Newest decisions go last.
    cases.pop(case_id, None)
    cases[case_id] = status
    while len(cases) > MAX_CASES_PER_PATTERN:
        cases.pop(next(iter(cases)))
    entry["updated_at"] = when


def forget(data: dict[str, Any], pattern: str, case_id: str) -> None:
    """Withdraw this case's lesson for a pattern (approval revoked)."""
    entry = data.get("patterns", {}).get(pattern)
    if entry:
        entry["cases"].pop(case_id, None)


def lesson_text(pattern: str, status: str, policy_version: str) -> str:
    """Privacy-safe lesson for AgentCore: fixed labels and the decision only."""
    verb = "confirmed" if status == "accepted" else "dismissed"
    return (
        f"Approved review lesson under policy {policy_version}: a reviewer {verb} "
        f'the finding "{pattern_label(pattern)}". Reviewers still decide each case; '
        "this is advisory context for similar findings."
    )


def _counts(
    entry: dict[str, Any] | None, exclude: str | None = None
) -> tuple[int, int]:
    statuses = [
        status
        for case_id, status in (entry or {}).get("cases", {}).items()
        if case_id != exclude
    ]
    return statuses.count("accepted"), statuses.count("dismissed")


def history(data: dict[str, Any], pattern: str, case_id: str) -> dict[str, Any]:
    """Decisions on this pattern in OTHER cases, with a hint if they lean clearly."""
    accepted, dismissed = _counts(data.get("patterns", {}).get(pattern), case_id)
    total = accepted + dismissed
    hint = None
    if total:
        cases = "case" if total == 1 else "cases"
        if dismissed / total >= LEAN:
            seen = f"Reviewers dismissed this in {dismissed} of {total} past {cases}."
            verdict = "Likely a false alarm, but you make the call."
        elif accepted / total >= LEAN:
            seen = f"Reviewers confirmed this in {accepted} of {total} past {cases}."
            verdict = "Likely a real issue; you make the call."
        else:
            seen = f"Reviewers have been split on this ({accepted} confirmed, {dismissed} dismissed)."
            verdict = "You make the call."
        if total < MIN_FOR_PATTERN:
            verdict = "One review is not a pattern yet; you make the call."
        hint = f"{seen} {verdict}"
    return dict(
        pattern_label=pattern_label(pattern),
        accepted=accepted,
        dismissed=dismissed,
        total=total,
        hint=hint,
    )


def summary(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for pattern, entry in data.get("patterns", {}).items():
        accepted, dismissed = _counts(entry)
        if accepted + dismissed:
            rows.append(
                dict(
                    pattern=pattern,
                    label=pattern_label(pattern),
                    accepted=accepted,
                    dismissed=dismissed,
                    total=accepted + dismissed,
                    updated_at=entry.get("updated_at"),
                )
            )
    return sorted(rows, key=lambda r: r.get("updated_at") or "", reverse=True)
