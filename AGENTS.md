# ClearPath contributor instructions

## Scope and safety

This repository is a local-first hackathon starter, not a production system. Read `README.md`, `docs/handoff.md`, and `docs/api-contract.md` before extending it. Preserve existing work and keep changes within the assigned frontend, backend, or infrastructure scope.

- Demo mode must work without AWS credentials or AWS network calls.
- Use synthetic data and explicitly fictional sample policies. Never claim official LPL endorsement or regulatory compliance.
- Do not deploy, bootstrap CDK, create resources, change IAM, commit, or push unless explicitly requested.
- Never commit secrets, local uploads, SQLite databases, or generated build/cache directories.
- Do not log raw document text, identifiers, or full Guardrails payloads. Privacy failures must stop model invocation; AWS failures must never fall back to demo results.

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
