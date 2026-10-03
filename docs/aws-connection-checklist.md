# Workshop AWS connection checklist

The initial `ClearPath` stack is deployed in account `033890317696`, region `us-east-1`, with CloudFormation status `UPDATE_COMPLETE`. Use this checklist before any redeployment, new resource creation, IAM change, provider change, or AgentCore runtime activation. The existing deployment is not blanket authorization for additional changes.

## Verified deployment facts

- [x] Deployment account: `033890317696`
- [x] Region: `us-east-1`
- [x] Private CloudFront/S3 frontend published at https://d5ztmc348hleb.cloudfront.net
- [x] Invite-only Cognito authorization code + PKCE sign-in works
- [x] API Gateway requires a Cognito access token with `clearpath/review`
- [x] Browser CORS preflight succeeds from the CloudFront origin
- [x] API requests without an access token return `401`
- [x] AgentCore Memory resource is provisioned
- [ ] Complete presigned upload, worker analysis, findings, review, and resume path live-validated
- [ ] Missing-scope behavior, logout/expiry behavior, and two-user ownership isolation live-validated
- [ ] Provider failure behavior and CloudWatch privacy review completed
- [ ] AgentCore runtime strategy ID reviewed and activated; currently it is **not configured**

## Confirm before future AWS changes

- [ ] Explicit organizer/account-owner authorization for the proposed change
- [ ] Temporary credential refresh/expiry procedure and cleanup owner
- [ ] Permission-boundary and SCP restrictions
- [ ] Exact approved Bedrock model or inference-profile identifier and destination model ARNs
- [ ] Guardrail ownership and approved published version
- [ ] S3, DynamoDB, Lambda, SQS, Textract, Bedrock, Cognito, CloudFront, and AgentCore quotas/costs
- [ ] Synthetic-only data handling, region residency, logging, and retention requirements
- [ ] AgentCore built-in semantic processing region constraints; the CDK confirmation flag does not pin processing to `us-east-1`
- [ ] Provenance, policy applicability, revocation, access isolation, and deletion controls before shared-memory activation

Use the standard boto3/AWS CLI credential chain outside this repository. Never place credentials in `.env`, frontend variables, source files, CDK context, shell history shared with others, or CloudFormation parameters. No AWS credentials are required for local demo mode.

Required AWS runtime settings are `AWS_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_GUARDRAIL_ID`, `BEDROCK_GUARDRAIL_VERSION`, `S3_DOCUMENT_BUCKET`, `DYNAMODB_CASES_TABLE`, and `WORKER_LAMBDA_FUNCTION_NAME`; CORS uses `CORS_ALLOWED_ORIGINS`.

The AgentCore lesson adapter can run only when both a Memory ID and concrete semantic strategy ID are supplied. In the current deployment, the Memory resource is provisioned but `agentcoreMemoryStrategyId` is not configured; Lambda has no AgentCore data-plane access, and no active AgentCore learning should be claimed. DynamoDB remains authoritative for review-memory eligibility and counts.

See [the deployment runbook](aws-deployment-runbook.md) for controlled synthesis, diff review, authorized updates, frontend publication, smoke tests, and retained-resource cleanup. AWS failures must never be replaced with demo findings.
