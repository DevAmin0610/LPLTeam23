# AWS deployment runbook

This runbook prepares an authorized hackathon deployment; it is not authorization to create resources. Commands below are examples and have **not** been run against AWS.

ClearPath is an independent synthetic-data prototype, not official LPL policy, an LPL-endorsed product, or a regulatory compliance guarantee.

## 1. Release gates

Do not deploy until all boxes are satisfied:

- [ ] Organizers authorize CDK bootstrap (if needed), CloudFormation deployment, IAM role creation, Cognito, CloudFront, S3, DynamoDB, Lambda, SQS, Textract, Bedrock Guardrails/model invocation, and AgentCore Memory.
- [ ] Account ID and target region are confirmed; this stack supports only `us-east-1`.
- [ ] Temporary credential refresh/expiry procedure and cleanup owner are known.
- [ ] Permission-boundary ARN and SCP restrictions are known.
- [ ] The exact Bedrock model or inference-profile identifier and all destination model ARNs are approved.
- [ ] Guardrail creation is allowed, or an existing guardrail ID and published numeric version are supplied.
- [ ] AgentCore Memory availability, quota, cost, retention, and built-in semantic processing regions are approved. The confirmation flag does not pin processing to one region.
- [ ] Only synthetic documents and fictional policies will be used.
- [ ] Frontend OAuth authorization-code + PKCE support is implemented and tested.
- [ ] Backend ownership/access enforcement is implemented and tested. Cognito authentication alone is insufficient.
- [ ] AgentCore ingestion/retrieval is implemented only for sanitized, structured, explicitly approved lessons, or the demo is labeled “Memory provisioned, integration pending.”
- [ ] Privacy failures stop model/Memory invocation; AWS failures do not fall back to demo findings.

The final three application gates are currently open in this repository. Do not expose the deployment to multiple users or claim live AgentCore learning until they are closed.

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

Review `infra/cdk.out/ClearPath.template.json` and the asset manifest. Check especially:

- no wildcard Bedrock model/guardrail resources;
- Textract’s unavoidable `*` resource is action-limited to `DetectDocumentText`;
- Lambda roles have only required S3, DynamoDB, Lambda, Bedrock, Textract and log permissions;
- no Lambda has AgentCore ingestion/retrieval permissions before the safe application workflow exists;
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

## 4. Bootstrap and deploy (authorized operator only)

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

## 5. Create the first invited reviewer

Creating users changes the AWS account and should be done by an authorized operator after deployment. Use the Cognito console or the approved `admin-create-user` process against the `UserPoolId` output. Do not create shared credentials or commit temporary passwords.

The user must set a permanent password at first login. Software-token MFA is available but optional in the hackathon stack; use the workshop’s required policy if it is stricter.

## 6. Publish the website last

Do this only after API/auth outputs exist and the frontend supports Cognito OAuth/PKCE.

Build-time public settings may include the API URL, Cognito domain, user-pool/client IDs, callback URL, and scope. They are identifiers, not secrets. Never embed AWS credentials or a Cognito client secret.

```sh
npm --prefix frontend run build
aws s3 sync frontend/dist/ s3://WEBSITE_BUCKET_NAME --delete --profile WORKSHOP_PROFILE --region us-east-1
aws cloudfront create-invalidation --distribution-id WEBSITE_DISTRIBUTION_ID --paths "/index.html" --profile WORKSHOP_PROFILE
```

CloudFront is intentionally static-only. The frontend calls the API Gateway URL directly. The SPA rewrite handles extensionless browser routes but excludes `/api`; there is no blanket error rewrite that could turn missing assets into HTML.

## 7. Smoke tests

Use synthetic data only.

1. Open the `WebsiteUrl` output over HTTPS. Confirm HTTP redirects to HTTPS.
2. Sign in as the invited user using authorization code + PKCE; verify logout and token expiry behavior.
3. Confirm an API call without an access token returns `401` and one without `clearpath/review` is denied.
4. Create and retrieve a synthetic case. Until server-side ownership is implemented, do not test with multiple users or expose the URL publicly.
5. Upload a small supported synthetic PDF through the presigned flow; reject wrong content type, oversize content, and a key not issued by the API.
6. Analyze a sample and confirm Textract/Guardrails/model failures surface as failures, never demo results.
7. Confirm no raw document text, identifiers, authorization headers, or full Guardrails payloads appear in CloudWatch logs.
8. Confirm the SQS failed-job destination receives terminal asynchronous failures during an intentional synthetic failure test.
9. Verify the AgentCore Memory resource and semantic strategy exist. Until backend integration is implemented, explicitly show that no Lambda role can call `CreateEvent` or `RetrieveMemoryRecords` and describe Memory as provisioned—not learning.
10. After safe integration exists, demonstrate one approved sanitized synthetic lesson influencing only a later explanation/next step while the underlying deterministic finding remains unchanged. Also test irrelevant, conflicting, revoked, privacy-blocked, and unavailable-Memory cases.

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
