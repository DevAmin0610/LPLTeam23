# ClearPath contributor instructions

## Scope and safety

This repository is a local-first hackathon starter, not a production system. Read `README.md`, `docs/product-direction.md`, `docs/handoff.md`, and `docs/api-contract.md` before extending it. Preserve existing work and keep changes within the assigned frontend, backend, or infrastructure scope.

- Demo mode must work without AWS credentials or AWS network calls.
- Use synthetic data and explicitly fictional sample policies. Never claim official LPL endorsement or regulatory compliance.
- Do not deploy, bootstrap CDK, create resources, change IAM, commit, or push unless explicitly requested.
- Never commit secrets, local uploads, SQLite databases, or generated build/cache directories.
- Do not log raw document text, identifiers, or full Guardrails payloads. Privacy failures must stop model invocation; AWS failures must never fall back to demo results.

## Product direction and memory

ClearPath reviews document packets and is intended to turn validated reviewer rationale into reusable institutional knowledge. See `docs/product-direction.md` for the proposed AgentCore Memory feedback loop, trust boundaries, and proof-of-concept scope.

- AgentCore Memory is planned, not implemented. Do not describe existing review notes or demo templates as a learning agent or live memory integration.
- Keep source evidence/case state, approved versioned rules, and advisory learned lessons separate. Memory must not override policy, alter deterministic findings, or approve cases.
- Require sanitization and explicit authorized approval before ingesting reusable lessons. Existing free-text review notes are not safe model/memory inputs. Enforce access isolation and preserve provenance, revocation, and applicable policy versions.
- AgentCore Memory does not require adopting AgentCore Runtime or a knowledge graph. Do not expand architecture without a concrete requirement.
- Workshop AWS use is restricted to `us-east-1`; verify model/memory processing constraints and do not assume cross-region inference is permitted.
- Never claim measured improvement, automatic training, or a percentage of mistakes eliminated without supporting evaluation.

## Format before handoff

**Run Ruff for Python and Prettier for supported frontend, infrastructure, JSON, and Markdown files whenever possible, after making changes and before handing off, committing, or pushing.**

From the repository root (after installing the documented dependencies):

```sh
npm run format
npm run format:check
```

These scripts run Prettier and `.venv/bin/ruff format`. For narrowly scoped work, format only your changed files to avoid touching a teammate's unrelated changes:

```sh
.venv/bin/ruff format backend/app/services/cases.py
npx --no-install prettier --write frontend/src/App.tsx
```

If formatting cannot run because tooling is unavailable, report that explicitly; do not claim the code is formatted. Do not use formatting to overwrite concurrent work or make unrelated changes. Re-run relevant checks after formatting.

## Validation

```sh
npm run test:backend
npm run test:frontend
npm run build
```

Backend tests include an in-process local HTTP smoke test. Infrastructure compilation is not deployment validation; AWS adapters and CDK deployment remain unverified. Do not claim tests passed without running them.

Keep the API contract, Python schemas, and TypeScript types aligned. Business rules belong in shared services, not HTTP handlers, Lambda handlers, UI code, or storage providers.
