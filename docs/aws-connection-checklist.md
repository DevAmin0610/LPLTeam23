# Workshop AWS connection checklist

Do not create resources, deploy, bootstrap CDK, or change IAM until organizers authorize it.

Ask organizers for:

- [ ] AWS account and region; is cross-region model inference allowed?
- [ ] Credential method: temporary access key/secret/session token, SSO, or an existing profile; session expiry/refresh instructions.
- [ ] Allowed Bedrock model IDs and whether model access is enabled.
- [ ] Required inference-profile ID or ARN (including destination model ARNs for IAM); `BEDROCK_MODEL_ID` may need a **workshop-provided model or inference-profile identifier**.
- [ ] Existing guardrail ID and published version; who may change it?
- [ ] Existing private S3 bucket, DynamoDB table/schema, worker Lambda, API endpoint/roles, KMS keys and networking constraints.
- [ ] Permission boundaries, SCP restrictions, allowed Textract/Bedrock/S3/DynamoDB/Lambda actions and role-creation policy.
- [ ] Whether creating any resources is permitted; CDK bootstrap role/account availability if permitted later.
- [ ] Data-handling rules, approved synthetic-only scope, region residency, logging/retention and guardrail assessment restrictions.
- [ ] Budget, service quotas, invocation limits and cleanup owner.
- [ ] Authentication and per-case authorization requirements before any shared/public access.
- [ ] Cognito user-pool/domain creation and email delivery limits; globally unique hosted-UI domain prefix.
- [ ] CloudFront distribution/OAC and private frontend-bucket creation, cache invalidations, and cleanup policy.
- [ ] AgentCore Memory availability, resource-creation permission, service quotas, retention/cost, encryption requirements, and exact data-plane IAM actions.
- [ ] Whether AgentCore built-in semantic extraction/consolidation processing outside `us-east-1` is permitted. The CDK confirmation flag is an acknowledgement, not a technical region pin.
- [ ] Existing AgentCore Memory ID/strategies/namespaces if organizers provide one; who owns records, revocation, deletion, and cleanup.

Fill `.env` from `.env.example` locally. Use the standard boto3 credential chain. For existing profiles, set `AWS_PROFILE` and `AWS_REGION`; for temporary credentials, configure them in the shell or AWS tooling **including the session token**, never in frontend code or committed files. Blank `AWS_PROFILE` permits environment/workload credentials. No credentials are required for demo mode.

Required runtime settings: `AWS_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_GUARDRAIL_ID`, `BEDROCK_GUARDRAIL_VERSION`, `S3_DOCUMENT_BUCKET`, `DYNAMODB_CASES_TABLE`, `WORKER_LAMBDA_FUNCTION_NAME`. CORS uses `CORS_ALLOWED_ORIGINS`.

The CDK stack now composes the existing AWS handlers and creates Cognito, CloudFront, and AgentCore Memory resources. Deployment is still gated: the frontend does not yet implement OAuth/PKCE or attach access tokens, the backend does not enforce case ownership from authenticated claims, and the backend still uses DynamoDB review history rather than AgentCore Memory. Do not expose it publicly or claim live semantic learning until those application integrations are implemented and tested.

See [the deployment runbook](aws-deployment-runbook.md) for context keys, synthesis review, authorized deployment, website publication, smoke tests, and retained-resource cleanup. No AWS errors may be replaced by demo findings.
