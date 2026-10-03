# ClearPath AWS infrastructure

TypeScript CDK for the hackathon AWS deployment. The stack is restricted to `us-east-1` and defines:

- private S3 document storage and a retained DynamoDB case table;
- FastAPI and worker Lambdas, an encrypted failed-job queue, and short-retention logs;
- Bedrock model/guardrail and Textract permissions scoped as far as those services allow;
- invite-only Cognito hosted UI and a JWT-protected HTTP API;
- AgentCore Memory, with semantic extraction enabled by default after an explicit processing-region confirmation;
- a private frontend bucket behind CloudFront Origin Access Control.

Nothing in this directory deploys automatically. Do not bootstrap or deploy until the temporary account owner authorizes resource creation, IAM roles, Cognito, CloudFront, Bedrock, and AgentCore Memory.

## Local validation

From `infra/`:

```sh
npm ci
npm test
```

From the repository root:

```sh
npm run format:check
npm run build
```

`npm run synth:local` packages the backend with local Python. `npm run synth` uses Lambda's Docker bundling image and may require Docker/network access. Both require the deployment context described below; neither creates AWS resources.

## Required deployment context

Use exact workshop-approved identifiers. The defaults are examples, not evidence of service/model access.

```sh
npm run synth:local -- \
  -c account=123456789012 \
  -c region=us-east-1 \
  -c modelId=WORKSHOP_MODEL_OR_INFERENCE_PROFILE \
  -c memoryProcessingRegionConfirmed=true \
  -c authDomainPrefix=clearpath-team23-unique
```

Important context keys:

| Key                                       | Default                     | Purpose                                                                                                                     |
| ----------------------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `account`, `region`                       | environment agnostic        | Deployment target. Concrete deployments must use `us-east-1`.                                                               |
| `modelId`                                 | `amazon.nova-lite-v1:0`     | Workshop-approved model ID or full inference-profile ARN.                                                                   |
| `additionalModelArns`                     | `[]`                        | Exact destination model ARNs required by an inference profile. Wildcards are rejected.                                      |
| `guardrailId`, `guardrailVersion`         | create retained guardrail   | Import both values together; version must be published and numeric.                                                         |
| `existingBucketName`, `existingTableName` | create retained resources   | Import organizer-provided resources without changing their configuration. Table partition key must be string `id`.          |
| `existingMemoryId`                        | create retained Memory      | Import an AgentCore Memory ID in this account/region. Import does not change its strategies or retention.                   |
| `enableSemanticMemory`                    | `true`                      | Create the built-in semantic strategy for approved lessons.                                                                 |
| `memoryProcessingRegionConfirmed`         | `false`                     | Required acknowledgement before semantic strategy synthesis. This does not technically pin model processing to `us-east-1`. |
| `memoryEventExpiryDays`                   | `7`                         | Raw event retention, integer 3–365 days. Extracted records have separate lifecycle semantics.                               |
| `frontendOrigins`                         | `["http://localhost:5173"]` | Additional exact origins for API/document CORS and OAuth callbacks. CloudFront is added automatically.                      |
| `authDomainPrefix`                        | account-derived             | Globally unique, lowercase Cognito domain prefix. Set it explicitly for predictable login URLs.                             |
| `permissionsBoundaryArn`                  | none                        | Existing workshop IAM permissions boundary applied to roles created by this stack.                                          |
| `apiFunctionName`, `workerFunctionName`   | generated                   | Optional fixed Lambda names.                                                                                                |
| `localBundling`                           | `false`                     | Use local Python packaging instead of Docker.                                                                               |

There is deliberately no unauthenticated-API switch.

## Authentication boundary

The user pool is admin/invite-only. Its browser client has no secret and uses OAuth authorization code flow (the frontend must use PKCE). API Gateway requires an access token containing `clearpath/review` on every route.

Infrastructure authentication is not case authorization. Before shared use, the backend must derive a stable principal from verified API Gateway claims, store ownership, and enforce it on every case, document, finding, memory, and reset operation. The current frontend also needs OAuth/PKCE token handling and must attach the access token as `Authorization: Bearer ...`; until that is implemented, the protected deployed API is intentionally unusable from the current UI.

## AgentCore Memory boundary

The stack provisions semantic Memory because it is part of the intended AWS demo, but it grants the API and worker **no AgentCore data-plane permissions yet**. The backend still uses `DynamoMemoryStore`; provisioning is not active integration.

Before calling `grantIngestion`, `grantRetrieval`, or `grantRevocation` from `lib/memory.ts`, implement and test an application workflow that:

1. stores reviews synchronously in the authoritative case store;
2. accepts structured rationale, not arbitrary existing free-text notes;
3. sanitizes before any AgentCore extraction/model call and fails closed on privacy errors;
4. requires explicit approval by an authorized reviewer;
5. records tenant scope, provenance, applicable policy/rule versions, approval and revocation state;
6. treats retrieved text as untrusted advisory context;
7. never lets Memory alter deterministic findings, approve a case, or waive policy;
8. handles asynchronous extraction, failed ingestion, stale lessons, deletion, and revocation honestly.

AWS documents that built-in semantic processing may use other US regions. `memoryProcessingRegionConfirmed=true` records a human deployment decision; it does not enforce `us-east-1`-only inference. If the workshop restriction prohibits that processing, either obtain an explicit exception/confirmation from organizers or synthesize with `-c enableSemanticMemory=false` and do not claim semantic Memory is active.

## CloudFront publication

CDK creates only the private bucket, CloudFront distribution, OAC, SPA rewrite function, and outputs. It intentionally does not run the frontend build or upload files from a deployment custom resource.

After an authorized stack deployment:

1. Build the frontend with the deployed API/auth settings once frontend OAuth support exists.
2. Upload `frontend/dist/` with `aws s3 sync`, using the `WebsiteBucketName` stack output.
3. Invalidate `/index.html` and any changed non-hashed files using the `WebsiteDistributionId` output.
4. Open `WebsiteUrl` and verify HTTPS, sign-in, authenticated API calls, logout, SPA refresh, and that `/api` is not proxied by CloudFront.

Do not put AWS credentials, a Cognito client secret, documents, or runtime configuration secrets in the frontend bundle. See `../docs/aws-deployment-runbook.md` for gated commands and smoke tests.
