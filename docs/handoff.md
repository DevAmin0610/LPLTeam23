# Team handoff — intentionally partial MVP

The user requested a minimal pushable baseline instead of finishing every original acceptance criterion. The local vertical slice works; the AWS stack/adapters are **draft, unverified integration code**, not a deployed system.

## Ownership boundaries

| Team           | Owns                | Next work                                                                                                                                                              |
| -------------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend       | `frontend/`         | Split the starter screen into components, refine accessibility/error handling, add browser E2E tests, improve document viewer and case navigation.                     |
| Backend        | `backend/`, `demo/` | AWS composition/handlers and presigned registration/completion, durable worker leases/retries, auth/case ownership, parser/privacy hardening and more tests.           |
| Infrastructure | `infra/`            | Validate synthesized template and packaging after handlers exist, workshop resource imports, permission boundaries, model/inference-profile IAM and deployment review. |

Coordinate changes to `backend/app/schemas/models.py`, `frontend/src/types.ts`, and `docs/api-contract.md`. Provider ports are in `backend/app/providers/interfaces.py`. HTTP and SDK dependencies do not belong in the rule engine.

## Current backend behavior

SQLite stores case/job/findings and separate review dictionaries. Machine publication never replaces reviews. Stable finding IDs are derived from case/run/rule; same-run duplicate delivery is a no-op. New runs use new IDs; prior decisions are retained but not applied automatically to different analyses. Pending/processing jobs are interrupted at local startup; use one local API process. No worker leases or AWS retry recovery are implemented yet.

Only labeled synthetic fields are parsed; conservative address normalization collapses whitespace and case only. Ambiguous/duplicate/unrecognized identifiers are flagged for review. Field values are compared before redaction, and explanation payloads are allowlisted deterministic text. Local evidence uses page navigation and withheld values, not invented coordinates. Accepted means the reviewer agrees, not that a correction is completed.

## AWS work intentionally deferred

`providers/aws/adapters.py` contains lazy boto3 draft adapters for Textract, ApplyGuardrail, Converse, S3, DynamoDB, and asynchronous Lambda dispatch. They are not connected to application startup and have not been tested against AWS. Review their behavior before enabling them; do not advertise live integration.

Required before switching modes:

1. Implement a composition factory separate from `main.py`; demo startup must never import or initialize AWS clients.
2. Implement API and worker handlers at the CDK-reserved paths. Do not create a local thread worker inside Lambda. Match handler lifecycle to AWS providers.
3. Implement case-bound presigned upload registration/completion, object-size/type validation and immutable source keys after finalization. The frontend client already has the intended API path; backend does not yet implement it.
4. Add lease/attempt ownership to worker claims, stale-job recovery, async failure reconciliation and bounded durable history. The current local claim is deliberately not sufficient for AWS retries.
5. Validate privacy behavior with mocked SDK blocked/masked/unchanged/error responses. Fail closed; never send raw IDs or source text to Converse or logs.
6. Authenticate and enforce server-side case access. CDK's default IAM authorizer is not an advisor login implementation and the frontend does not sign requests.
7. Verify S3/DynamoDB limits, API Gateway PDF delivery, guardrail and model/profile permission details and package size.

## Infrastructure status

CDK definitions include private S3, DynamoDB, HTTP API, API/worker Lambdas, guardrail and scoped IAM. Existing bucket/table/guardrail identifiers can be supplied through context. No live lookups are needed. **Packaging deliberately fails until the missing Lambda handler files exist.** Only TypeScript compilation is part of this starter validation; no deployment or bootstrap should be run. `infra/test/` is reserved for infrastructure assertions.

## Known local limitations

No browser automation, no general PDF/layout recognition, no replacement/deletion endpoints, no multipage/OCR, no real LLM, no production PII detection, no vector ingestion, no redacted PDF export, no auth, no retention or audit-grade history. Upload limits are enforced after multipart parsing, so do not expose this API publicly. A document failure produces partial review-required results, never a clean case.
