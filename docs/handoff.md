# Team handoff — intentionally partial MVP

The local vertical slice works. AWS adapters, composition, Lambda handlers and expanded CDK resources now exist, but remain **unverified integration code**, not a deployed system.

## Product direction: planned reviewer-feedback memory loop

Read [the product direction](product-direction.md) before extending this starter. The team plans to explore AgentCore Memory to turn validated reviewer rationale into sanitized, explicitly approved reusable lessons. The initial proof of concept should improve explanations and suggested next steps for similar synthetic cases, not change deterministic findings or approve cases.

No memory integration, lesson approval workflow, or structured review reason exists yet. Current free-text notes must not be ingested directly. Plan access isolation, provenance, policy-version applicability, revocation, asynchronous extraction, and evaluation before implementing shared memory. AgentCore Runtime and a knowledge graph are not prerequisites. Workshop AWS processing is restricted to `us-east-1`; confirm all model/memory processing constraints.

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

`providers/aws/adapters.py` contains lazy boto3 adapters for Textract, ApplyGuardrail, Converse, S3, DynamoDB, and asynchronous Lambda dispatch. AWS composition and Lambda handlers now connect them, but they have not been tested against AWS. Review their behavior before enabling them; do not advertise live integration.

Required before switching modes:

1. Live-validate the separate AWS composition and API/worker Lambda handler lifecycle; demo startup must never import or initialize AWS clients.
2. Live-validate case-bound presigned upload registration/completion, object-size/type validation and immutable source keys after finalization.
3. Live-validate worker lease/attempt ownership, stale-job recovery, asynchronous failure reconciliation and bounded durable history under Lambda retries.
4. Validate privacy behavior with mocked SDK blocked/masked/unchanged/error responses. Fail closed; never send raw IDs or source text to Converse or logs.
5. Complete Cognito OAuth/PKCE in the frontend and enforce server-side case access from verified claims. API Gateway JWT authentication alone is not case authorization.
6. Implement sanitized, explicitly approved AgentCore lesson ingestion/retrieval and revocation before claiming live semantic learning.
7. Verify S3/DynamoDB limits, API Gateway PDF delivery, guardrail and model/profile permission details and package size.

## Infrastructure status

CDK definitions include private S3, DynamoDB, JWT-protected HTTP API, Cognito, API/worker Lambdas, guardrail, AgentCore Memory, private CloudFront hosting and scoped IAM. Existing bucket/table/guardrail/Memory identifiers can be supplied through context. No live lookups are needed. Packaging includes the implemented Lambda handlers, and infrastructure assertions cover authentication, Memory and hosting. No deployment or bootstrap has been run; follow `aws-deployment-runbook.md` only after authorization.

## Known local limitations

No browser automation, no general PDF/layout recognition, no replacement/deletion endpoints, no multipage/OCR, no real LLM, no production PII detection, no vector ingestion, no redacted PDF export, no auth, no retention or audit-grade history. Upload limits are enforced after multipart parsing, so do not expose this API publicly. A document failure produces partial review-required results, never a clean case.
