# ClearPath — reviewer-assisted document checks

ClearPath reviews synthetic transfer-document packets, identifies missing information and discrepancies, presents source evidence, and lets a human reviewer accept or dismiss each finding.

## Current status

ClearPath supports two deliberately separate modes:

- **Local demo mode:** credential-free, network-free operation with committed synthetic PDFs, SQLite, local file storage, deterministic extraction/rules, and simulated explanation templates. It makes no AWS calls.
- **Deployed AWS mode:** invite-only Cognito authorization code + PKCE, a JWT-protected HTTP API, per-user case ownership, private S3 document and website buckets, DynamoDB case state, API/worker Lambdas, Textract/Guardrails/Bedrock adapters, CloudFront hosting, and a provisioned AgentCore Memory resource.

The `ClearPath` CloudFormation stack is deployed in account `033890317696`, `us-east-1`, with status `UPDATE_COMPLETE`. The authenticated frontend is published at **https://d5ztmc348hleb.cloudfront.net**. Cognito sign-in, HTTPS hosting, JWT-protected frontend/API connectivity, CORS preflight behavior, and unauthenticated API rejection (`401`) have been live-verified.

The complete AWS upload → analyze → review workflow, provider failure behavior, two-user ownership isolation, and operational/privacy checks still require live end-to-end validation before broader use. This is hackathon-ready, not production-ready.

## Features

- React/Vite/TypeScript review workspace with Cognito and local-demo authentication modes.
- Case creation, PDF upload, durable analysis status, polling, source-document viewing, and resumable case IDs.
- Findings for missing fields, identifier mismatches, address differences, and unsupported/review-required documents.
- Human accept/dismiss decisions, optional notes, evidence navigation, and a correction checklist.
- Privacy-safe model-input preview containing comparison outcomes rather than source identifiers.
- Explicit **Remember this decision** approval that stores only a finding pattern and decision—not reviewer notes or source values.
- Versioned deterministic sample rules and conservative extraction for supported synthetic, text-based PDFs.
- Fail-closed privacy checks; AWS failures never fall back to fabricated demo results.
- Invite-only Cognito, scoped access tokens, server-side case ownership, private S3, retained DynamoDB, and CloudFront Origin Access Control.
- AgentCore Memory provisioning and optional adapter wiring. The deployed Memory resource is **provisioned but not active** because no runtime semantic strategy ID is configured; DynamoDB remains authoritative for review-memory counts.
- Twelve committed synthetic PDFs across four reusable local demo packets, with a reproducible generator.

## Run the local demo

Requirements: Python 3.12+, Node.js 22.12+ (or 24), and npm.

```sh
python -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cp .env.example .env
npm ci
npm --prefix frontend ci
npm --prefix infra ci
```

Terminal 1, from the repository root:

```sh
.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Terminal 2:

```sh
npm --prefix frontend run dev
```

Open **http://localhost:5173**. Use `localhost`, not `127.0.0.1`, for the configured browser origin. API docs are at http://localhost:8000/docs. The local frontend uses demo authentication (`reviewer` / `LPLTeam23`). Run one backend process without reload because the local job queue is in-process.

Select a synthetic packet and choose **Load sample case**, or create a case and upload one supported PDF per document type. Demo mode stores state in gitignored `local-data/` and never initializes AWS clients.

See [`DEMO.md`](DEMO.md) for the guided local walkthrough.

## Deployed AWS mode

The deployed frontend uses build-time public identifiers for API Gateway and Cognito; it contains no AWS credentials or Cognito client secret. Access is invite-only. AWS mode hides local sample-loading controls and requires users to create a synthetic case and use the presigned upload flow.

Current verified deployment facts:

- CloudFormation stack: `ClearPath` / `UPDATE_COMPLETE`
- Region: `us-east-1`
- Frontend: https://d5ztmc348hleb.cloudfront.net
- API: Cognito JWT protected with `clearpath/review`
- HTTP → HTTPS redirect: verified
- Cognito authorization-code + PKCE sign-in: verified
- Browser CORS preflight: verified
- API request without access token: `401`, verified
- AgentCore Memory: resource provisioned; Lambda runtime ingestion/retrieval inactive without `agentcoreMemoryStrategyId`

Follow [`docs/aws-deployment-runbook.md`](docs/aws-deployment-runbook.md) for controlled updates, publication, smoke checks, and cleanup. Deployment, IAM changes, new resources, or AgentCore runtime activation still require explicit authorization.

## Architecture and contracts

- Backend schemas: `backend/app/schemas/models.py`
- Frontend types: `frontend/src/types.ts`
- API contract: [`docs/api-contract.md`](docs/api-contract.md)
- Product and memory boundaries: [`docs/product-direction.md`](docs/product-direction.md)
- Current handoff/status: [`docs/handoff.md`](docs/handoff.md)
- AWS infrastructure: [`infra/README.md`](infra/README.md)

Business rules live in shared services rather than HTTP handlers, Lambda handlers, UI code, or storage adapters. Demo startup must never import or initialize AWS clients.

## Validation and formatting

```sh
npm run format
npm run format:check
npm run test:backend
npm run test:frontend
npm run build
npm --prefix infra test
```

Backend tests include an in-process local HTTP smoke path covering sample loading, analysis polling, document retrieval, reviews, privacy failures, and retry behavior. Infrastructure assertions cover authentication, private hosting, AgentCore provisioning, and the unauthenticated CORS preflight exception. There is no automated browser end-to-end suite yet.

Regenerate the committed synthetic fixtures with:

```sh
.venv/bin/python demo/generate.py
```

## Boundaries

- Supported demo inputs are small, single-page, unencrypted, text-based PDFs using canonical or versioned synthetic label aliases; maximum 5 MB per file.
- Scanned, image-containing, unreadable, multipage, encrypted, or unsupported layouts require manual review.
- Local masking recognizes only the synthetic identifier formats and is not production-grade PII detection.
- Raw synthetic PDFs are visible in the source viewer; excerpts and model inputs omit source values.
- Case names and reviewer notes are not privacy-filtered. Never put sensitive information in them.
- Local demo authentication is a frontend-only gate and must never be publicly exposed.
- Shared review memory is not tenant-isolated. Complete provenance, policy applicability, revocation, retention, and role-based lesson approval remain future work.
- AgentCore lessons are advisory only and must never change deterministic findings, waive policy, or approve cases.
- Do not claim measured accuracy improvement, regulatory compliance, official endorsement, or active AgentCore learning without supporting validation.
