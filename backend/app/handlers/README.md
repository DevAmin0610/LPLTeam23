# Lambda handoff

Reserved entrypoints: `app.handlers.api.handler` (Mangum) and `app.handlers.worker.handler` (separate async Lambda calling `CaseService.process`). These handlers are deliberately not implemented in this local starter. CDK packaging refuses to proceed until they exist. Do not point Lambda at the local composition root: it creates a local executor and SQLite recovery lifecycle.

Before implementing, add an AWS composition root, presigned upload registration/completion, worker leases and recovery, authentication and case authorization. See `docs/handoff.md`.
