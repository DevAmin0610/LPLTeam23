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

Fill `.env` from `.env.example` locally. Use the standard boto3 credential chain. For existing profiles, set `AWS_PROFILE` and `AWS_REGION`; for temporary credentials, configure them in the shell or AWS tooling **including the session token**, never in frontend code or committed files. Blank `AWS_PROFILE` permits environment/workload credentials. No credentials are required for demo mode.

Required runtime settings: `AWS_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_GUARDRAIL_ID`, `BEDROCK_GUARDRAIL_VERSION`, `S3_DOCUMENT_BUCKET`, `DYNAMODB_CASES_TABLE`, `WORKER_LAMBDA_FUNCTION_NAME`. CORS uses `CORS_ALLOWED_ORIGINS`.

AWS mode is not enabled in this handoff. Missing settings are reported explicitly; even with settings supplied startup refuses until the backend team completes composition. No AWS errors may be replaced by demo findings.
