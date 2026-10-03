# ClearPath — local-first team starter

A runnable **starter**, deliberately stopped short of the full MVP for frontend/backend/infrastructure team handoff. Independent LPL Financial hackathon prototype; **not endorsed by LPL, not actual LPL policy, and not a regulatory compliance guarantee**. Use synthetic data only.

## Product direction

ClearPath is intended to turn **validated reviewer rationale into reusable institutional knowledge**: approved, sanitized lessons from prior document reviews could help explain recurring issues and suggest better next steps without fine-tuning the model. AgentCore Memory is a **planned proof of concept, not an implemented integration**. Lessons are advisory; source evidence and versioned rules remain authoritative.

Read [the product direction](docs/product-direction.md) for the feedback loop, privacy boundaries, and evaluation scope. The current starter stores review decisions and notes but does not learn from them or send them to memory.

## Run locally

Requirements: Python 3.12+, Node.js 22.12+ (or 24), npm. From the repository root:

```sh
python -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cp .env.example .env
npm ci
npm --prefix frontend ci
npm --prefix infra ci
```

Terminal 1, repository root:

```sh
.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Terminal 2, repository root:

```sh
npm --prefix frontend run dev
```

Open **http://localhost:5173** (use localhost, not 127.0.0.1, for the configured CORS origin). API docs: http://localhost:8000/docs. Frontend defaults to `VITE_API_BASE_URL=http://localhost:8000`; override in `frontend/.env` if needed. Run just **one backend process/worker**, without reload, for the local job queue.

Select a sample and **Load sample case**. This uploads the committed synthetic PDFs into local storage, queues analysis, and polls for actual results. Inspect a PDF and sanitized evidence, accept/dismiss findings, and view the correction checklist. You can also create a case and upload PDFs individually. One PDF per type; create a new case to replace a packet.

## Implemented local slice

- React/Vite/TypeScript review screen, upload, samples, source viewer, polling, review notes, checklist, model-input preview.
- FastAPI/Pydantic API with shared contracts, SQLite persistence and gitignored `local-data/uploads/`.
- Background executor, durable job status, startup interruption recovery; no AWS calls in demo mode.
- Real `pypdf` extraction and versioned sample rules for missing fields, SSN/account mismatches, and address differences.
- Protected comparisons before sanitization; deterministic explanation templates; input/output privacy checks that fail closed.
- Nine downloadable, synthetic PDFs across three packets; reproducible generator.
- Provider ports, AWS adapters/composition and Lambda handlers; CDK resources for the runtime, Cognito, AgentCore Memory and CloudFront. **No resources have been deployed or live-validated.**

## Checks and formatting

```sh
npm run format
npm run format:check
npm run test:backend
npm run test:frontend
npm run build
```

Backend tests include an in-process HTTP end-to-end smoke path (sample loading, analysis polling, document retrieval and saved reviews), fixture findings, privacy failure and retry behavior. There is no automated browser E2E suite yet.

To regenerate the committed fixtures:

```sh
.venv/bin/python demo/generate.py
```

## Boundaries and handoff

Read [the handoff](docs/handoff.md), [API contract](docs/api-contract.md), and [AWS checklist](docs/aws-connection-checklist.md).

- Demo extraction supports small, single-page, unencrypted **text-based** PDFs with exact sample field labels. Scanned/image-containing, unreadable, multipage and unsupported layouts require manual review. Max 5 MB/file.
- Local masking supports the synthetic identifier formats only; **not production-grade PII detection**. The raw synthetic PDF is deliberately visible in the source viewer; excerpts and model inputs omit values. User-entered case names and review notes are not privacy-filtered: never put sensitive information in them.
- Local demo mode has no authentication. The AWS infrastructure defines invite-only Cognito and JWT-protected API Gateway access, but the frontend OAuth/PKCE flow and backend case ownership checks are not implemented. Authentication, UUIDs and CORS are not case authorization; do not expose the deployment publicly until those controls, upload/body limits, security review and operational controls are complete.
- Standard AWS credential chain will be used by the draft lazy adapters. Keep temporary credentials/profile configuration outside this repository. No AWS credentials belong in the frontend.
- `APP_MODE=aws` validates required settings and uses the AWS composition; it never silently falls back to demo.
- AgentCore Memory provisioning is implemented, but the backend still uses its DynamoDB review-history store. Do not claim live semantic learning until approved/sanitized ingestion and retrieval are integrated.
- No resources deployed, no IAM changes, no CDK bootstrap. Follow `docs/aws-deployment-runbook.md` only after workshop authorization and all release gates are satisfied.
