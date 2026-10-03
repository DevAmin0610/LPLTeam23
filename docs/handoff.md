# Team handoff — deployed hackathon prototype

The local vertical slice works, and the AWS stack is deployed in account `033890317696`, `us-east-1`, with CloudFormation status `UPDATE_COMPLETE`. The frontend is published at https://d5ztmc348hleb.cloudfront.net. Cognito sign-in, protected frontend/API connectivity, CORS preflight handling, and unauthenticated rejection are verified; the complete AWS case workflow remains unvalidated.

## Product direction: planned reviewer-feedback memory loop

Read [the product direction](product-direction.md) before extending this starter. The team is exploring AgentCore Memory to turn validated reviewer rationale into sanitized, explicitly approved reusable lessons. The initial proof of concept should improve explanations and suggested next steps for similar synthetic cases, not change deterministic findings or approve cases.

An opt-in AgentCore lesson adapter and explicit `remember` approval now exist. It sends fixed pattern/status lesson text, never free-text review notes or source values, and retrieved lessons affect explanations only. A concrete semantic strategy ID is required before CDK grants runtime access. Tenant isolation, role-based approval, complete provenance/policy-version applicability, revocation, asynchronous status and evaluation remain future work; do not enable shared multi-user memory until those controls are complete. AgentCore Runtime and a knowledge graph are not prerequisites. Workshop AWS processing is restricted to `us-east-1`; confirm all model/memory processing constraints.

## Ownership boundaries

| Team           | Owns                | Next work                                                                                                                                             |
| -------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend       | `frontend/`         | Add browser E2E coverage, refine accessibility/error recovery, and improve document viewing and case navigation.                                      |
| Backend        | `backend/`, `demo/` | Live-validate presigned uploads and worker processing; harden parser/privacy behavior, retries, limits, failure reconciliation, and operational logs. |
| Infrastructure | `infra/`            | Validate provider permissions and limits, two-user ownership, monitoring/failure destinations, and controlled AgentCore runtime activation.           |

Coordinate changes to `backend/app/schemas/models.py`, `frontend/src/types.ts`, and `docs/api-contract.md`. Provider ports are in `backend/app/providers/interfaces.py`. HTTP and SDK dependencies do not belong in the rule engine.

## Current backend behavior

SQLite stores case/job/findings and separate review dictionaries. Machine publication never replaces reviews. Stable finding IDs are derived from case/run/rule; same-run duplicate delivery is a no-op. New runs use new IDs; prior decisions are retained but not applied automatically to different analyses. Pending/processing jobs are interrupted at local startup; use one local API process. Local and DynamoDB workers use owner-checked leases, renew them between processing stages, and permit recovery after expiry.

Only labeled synthetic fields are parsed; conservative address normalization collapses whitespace and case only. Ambiguous/duplicate/unrecognized identifiers are flagged for review. Field values are compared before redaction, and explanation payloads are allowlisted deterministic text. Local evidence uses page navigation and withheld values, not invented coordinates. Accepted means the reviewer agrees, not that a correction is completed.

## AWS integration validation still required

`providers/aws/adapters.py` contains lazy boto3 adapters for Textract, ApplyGuardrail, Converse, S3, DynamoDB, and asynchronous Lambda dispatch. The stack and basic authenticated frontend/API path are live, including the deployed CORS preflight route. Textract, Guardrails, Bedrock, presigned upload, worker processing, and the complete review path have not yet been validated end to end; do not advertise those integrations as proven.

Required before claiming a validated AWS workflow or expanding access:

1. Live-validate the separate AWS composition and API/worker Lambda handler lifecycle; demo startup must never import or initialize AWS clients.
2. Live-validate case-bound presigned upload registration/completion, object-size/type validation and immutable source keys after finalization.
3. Live-validate worker lease/attempt ownership and stale-job recovery under Lambda retries; asynchronous failure reconciliation and bounded durable history remain incomplete.
4. Validate privacy behavior with mocked SDK blocked/masked/unchanged/error responses. Fail closed; never send raw IDs or source text to Converse or logs.
5. Cognito authorization code + PKCE sign-in and bearer-token frontend/API calls are validated. Still validate logout, token expiry, required-scope behavior, and server-side ownership using two invited synthetic-demo users.
6. Live-validate sanitized, explicitly approved AgentCore lesson ingestion/retrieval, then add authoritative provenance, policy applicability and revocation before shared use or claims of live semantic learning.
7. Verify S3/DynamoDB limits, API Gateway PDF delivery, guardrail and model/profile permission details and package size.

## Infrastructure status

CDK provisions private S3, DynamoDB, a JWT-protected HTTP API, Cognito, API/worker Lambdas, a guardrail, AgentCore Memory, private CloudFront hosting, and scoped IAM. The `ClearPath` stack is deployed and the frontend is published. AgentCore Memory is provisioned without a configured runtime strategy ID, so Lambda ingestion/retrieval permissions are inactive. Existing resource identifiers can also be supplied through context, and no live lookups are required. Follow `aws-deployment-runbook.md` for authorized updates and remaining validation.

## Known local limitations

No browser automation, no general PDF/layout recognition, no replacement/deletion endpoints, no multipage/OCR, no real LLM, no production PII detection, no vector ingestion, no redacted PDF export, no auth, no retention or audit-grade history. Upload limits are enforced after multipart parsing, so do not expose this API publicly. A document failure produces partial review-required results, never a clean case.
