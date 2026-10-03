# Lambda handlers

Deployed entrypoints:

- `app.handlers.api.handler`: Mangum adapter for the FastAPI AWS composition.
- `app.handlers.worker.handler`: asynchronous worker entrypoint calling `CaseService.process`.

The handlers use the AWS composition root, presigned upload registration/completion, DynamoDB-backed case state and leases, S3 document storage, verified API Gateway claims, and per-user case ownership. They are packaged by CDK and deployed in the `ClearPath` stack in `us-east-1`.

Cognito sign-in and the protected frontend/API path are live-verified. The complete presigned upload, Textract, Guardrails, Bedrock, worker, findings, and review workflow still requires end-to-end validation. Never point Lambda at the local composition root: it creates the local executor and SQLite recovery lifecycle. See `docs/handoff.md` and `docs/aws-deployment-runbook.md`.
