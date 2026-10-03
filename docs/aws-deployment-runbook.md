# AWS deployment runbook

The `ClearPath` stack is deployed in account `033890317696`, `us-east-1`, with CloudFormation status `UPDATE_COMPLETE`, and the frontend is published at https://d5ztmc348hleb.cloudfront.net. This runbook is the controlled procedure for future authorized updates and republication; commands must not be rerun blindly or treated as authorization.

ClearPath is an independent synthetic-data prototype, not official LPL policy, an LPL-endorsed product, or a regulatory compliance guarantee.

## 1. Deployment status and gates for future updates

Verified in the current deployment:

- [x] CloudFormation stack deployment completed in account `033890317696`, `us-east-1`.
- [x] Frontend published through private S3 and CloudFront with HTTP redirected to HTTPS.
- [x] Invite-only Cognito authorization code + PKCE sign-in completed successfully.
- [x] JWT-protected frontend/API connectivity and CORS preflight handling verified.
- [x] API request without an access token returns `401`.
- [x] AgentCore Memory resource provisioned; runtime strategy ID and Lambda data-plane access remain disabled.

Before any future deployment or runtime activation:

- [ ] Organizers authorize CDK bootstrap (if needed), CloudFormation deployment, IAM role creation, Cognito, CloudFront, S3, DynamoDB, Lambda, SQS, Textract, Bedrock Guardrails/model invocation, and AgentCore Memory.
- [ ] Account ID and target region are confirmed; this stack supports only `us-east-1`.
- [ ] Temporary credential refresh/expiry procedure and cleanup owner are known.
- [ ] Permission-boundary ARN and SCP restrictions are known.
- [ ] The exact Bedrock model or inference-profile identifier and all destination model ARNs are approved.
- [ ] Guardrail creation is allowed, or an existing guardrail ID and published numeric version are supplied.
- [ ] AgentCore Memory availability, quota, cost, retention, and built-in semantic processing regions are approved. The confirmation flag does not pin processing to one region.
- [ ] Only synthetic documents and fictional policies will be used.
- [x] Frontend OAuth authorization-code + PKCE and backend ownership enforcement are implemented and covered by offline tests.
- [ ] Logout, token expiry, missing-scope behavior, and two-user ownership are live-validated in the deployed environment.
- [ ] AgentCore ingestion/retrieval is implemented only for sanitized, structured, explicitly approved lessons, or the demo is labeled “Memory provisioned, integration pending.”
- [ ] Privacy failures stop model/Memory invocation; AWS failures do not fall back to demo findings.

Basic browser sign-in and protected API connectivity are validated. Complete authentication/authorization behavior, the upload/analyze/review workflow, shared-memory isolation, and lesson provenance/revocation remain open. Keep the hosted application invite-only and synthetic, and do not claim active AgentCore learning or a validated end-to-end AWS workflow.

## 2. Validate without AWS calls

From the repository root:

```sh
npm ci
npm --prefix frontend ci
npm --prefix infra ci
npm run format:check
npm run test:backend
npm run test:frontend
npm run build
npm --prefix infra test
```

Synthesize locally with concrete, organizer-approved values:

```sh
npm --prefix infra run synth:local -- \
  -c account=123456789012 \
  -c region=us-east-1 \
  -c modelId=WORKSHOP_MODEL_OR_PROFILE \
  -c additionalModelArns='["EXACT_DESTINATION_MODEL_ARN"]' \
  -c memoryProcessingRegionConfirmed=true \
  -c authDomainPrefix=clearpath-team23-unique \
  -c permissionsBoundaryArn=arn:aws:iam::123456789012:policy/WORKSHOP_BOUNDARY
```

Omit `additionalModelArns` or `permissionsBoundaryArn` only when organizers confirm they are unnecessary. To import resources, add the relevant `existingBucketName`, `existingTableName`, `guardrailId` plus `guardrailVersion`, or `existingMemoryId` context.

Memory provisioning and runtime activation are deliberately separate. Without `agentcoreMemoryStrategyId`, the stack can provision semantic Memory but gives neither Lambda AgentCore data-plane access. After an authorized operator obtains the concrete strategy ID from the provisioned or imported Memory, synthesize and review a second change with `-c agentcoreMemoryStrategyId=APPROVED_STRATEGY_ID`. That change injects the Memory/strategy IDs, grants the API ingestion and retrieval, and grants the worker retrieval. Never guess the generated strategy ID.

Review `infra/cdk.out/ClearPath.template.json` and the asset manifest. Check especially:

- no wildcard Bedrock model/guardrail resources;
- Textract’s unavoidable `*` resource is action-limited to `DetectDocumentText`;
- Lambda roles have only required S3, DynamoDB, Lambda, Bedrock, Textract and log permissions;
- no Lambda has AgentCore ingestion/retrieval permissions unless `agentcoreMemoryStrategyId` was explicitly supplied;
- when runtime Memory is enabled, the API has ingestion/retrieval, the worker has retrieval, and neither role has deletion;
- all stateful resources are retained and the account cleanup owner understands the consequence;
- the document and website buckets block public access;
- API Gateway’s default route requires JWT plus `clearpath/review` scope;
- Cognito self-registration is disabled and the browser client has no secret;
- CloudFront has only the static S3 origin, not an API origin.

## 3. Credential and account check

Use the workshop’s standard credential flow outside this repository. Never place credentials in `.env`, frontend variables, source files, CDK context, shell history shared with others, or CloudFormation parameters.

With explicit organizer authorization, check the active identity and region before any write:

```sh
aws sts get-caller-identity --profile WORKSHOP_PROFILE --region us-east-1
aws configure get region --profile WORKSHOP_PROFILE
```

Stop if the account or region differs from the reviewed synth.

## 4. Bootstrap or deploy an authorized update

CDK bootstrap creates account-level resources and IAM roles. Skip it if organizers provide an approved existing bootstrap environment. Otherwise, run it only with explicit permission and the workshop-required boundary/qualifier settings.

After approval, deploy using the exact same context reviewed during synthesis:

```sh
npm --prefix infra exec cdk deploy -- \
  --app "node dist/bin/clearpath.js" \
  --require-approval broadening \
  -c account=123456789012 \
  -c region=us-east-1 \
  -c modelId=WORKSHOP_MODEL_OR_PROFILE \
  -c additionalModelArns='["EXACT_DESTINATION_MODEL_ARN"]' \
  -c memoryProcessingRegionConfirmed=true \
  -c authDomainPrefix=clearpath-team23-unique \
  -c permissionsBoundaryArn=arn:aws:iam::123456789012:policy/WORKSHOP_BOUNDARY
```

Do not use `--require-approval never`. Inspect the CloudFormation change set before confirmation. Record outputs without committing them.

## 5. Create an invited reviewer

Creating users changes the AWS account and should be done by an authorized operator after deployment. Use the Cognito console or the approved `admin-create-user` process against the `UserPoolId` output. Do not create shared credentials or commit temporary passwords.

The user must set a permanent password at first login. Software-token MFA is available but optional in the hackathon stack; use the workshop’s required policy if it is stricter.

## 6. Build or republish the website

The current website is https://d5ztmc348hleb.cloudfront.net. Build or republish only after the API, `AuthDomain`, `UserPoolClientId`, `WebsiteUrl`, website bucket, and distribution outputs exist and match the reviewed deployment.

Build-time public settings may include the API URL, Cognito domain, client ID, callback URL and scope. They are identifiers, not secrets. Never embed AWS credentials or a Cognito client secret. The redirect URI must exactly match the `WebsiteUrl` registered by CDK.

```sh
VITE_AUTH_MODE=cognito \
VITE_API_BASE_URL=API_URL \
VITE_COGNITO_DOMAIN=AUTH_DOMAIN \
VITE_COGNITO_CLIENT_ID=USER_POOL_CLIENT_ID \
VITE_COGNITO_REDIRECT_URI=WEBSITE_URL \
VITE_COGNITO_SCOPE="openid email clearpath/review" \
npm --prefix frontend run build

aws s3 sync frontend/dist/ s3://WEBSITE_BUCKET_NAME --delete --profile WORKSHOP_PROFILE --region us-east-1
aws cloudfront create-invalidation --distribution-id WEBSITE_DISTRIBUTION_ID --paths "/index.html" --profile WORKSHOP_PROFILE
```

CloudFront is intentionally static-only. The frontend calls the API Gateway URL directly. The SPA rewrite handles extensionless browser routes but excludes `/api`; there is no blanket error rewrite that could turn missing assets into HTML.

## 7. Smoke tests

Use synthetic data only.

1. **Verified:** open the `WebsiteUrl` output over HTTPS; HTTP redirects to HTTPS.
2. **Partially verified:** invited-user authorization code + PKCE sign-in and authenticated API connectivity work. Logout and token-expiry behavior remain to be validated.
3. **Partially verified:** an API call without an access token returns `401`. A token without `clearpath/review` still needs explicit denial testing.
4. Create and retrieve a synthetic case, then verify a second invited user receives `404` for that case on every protected case route.
5. Upload a small supported synthetic PDF through the presigned flow; reject wrong content type, oversize content, and a key not issued by the API.
6. Analyze a sample and confirm Textract/Guardrails/model failures surface as failures, never demo results.
7. Confirm no raw document text, identifiers, authorization headers, or full Guardrails payloads appear in CloudWatch logs.
8. Confirm the SQS failed-job destination receives terminal asynchronous failures during an intentional synthetic failure test.
9. **Verified provisioning state:** the AgentCore Memory resource and built-in semantic strategy exist. `agentcoreMemoryStrategyId` is not configured, Lambda has no `CreateEvent` or `RetrieveMemoryRecords` access, and Memory must be described as provisioned—not active.
10. After separately reviewing and deploying runtime activation, demonstrate one approved sanitized synthetic lesson influencing only a later explanation/next step while the underlying deterministic finding remains unchanged. Also test irrelevant, conflicting, privacy-blocked and unavailable-Memory cases. Revocation is not complete, so keep the proof of concept single-user and synthetic.

## 8. Rollback and cleanup

Because document storage, case data, Guardrails, Cognito, logs, queues, and AgentCore Memory are retained, deleting the CloudFormation stack is not complete cleanup. Before any deletion:

- export only non-sensitive evidence needed by hackathon rules;
- revoke user access and stop frontend publication;
- invalidate CloudFront if necessary;
- follow the documented application revocation/deletion process for Memory records and source events;
- identify imported resources that must never be deleted;
- have the cleanup owner enumerate retained resources and costs;
- obtain authorization before deleting data or resources.

Never weaken retention/removal policies simply to make teardown convenient. For a temporary account, organizers may prefer account closure as the final cleanup mechanism.
