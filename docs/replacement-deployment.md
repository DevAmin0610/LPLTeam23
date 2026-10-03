# Deploy detection fixes and document replacement

Apply this incremental patch on the branch that already contains the Packet B
fix. It adds replacement to the existing presigned upload/completion routes,
updates the frontend, and protects PDF fixtures from Git text conversion.

## Validation

From PowerShell with the virtual environment active:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

Expected for this checkout: 53 backend tests and 18 frontend tests pass. The
ordinary frontend build above validates compilation only; do not publish it
without the existing production Cognito/API settings.

## Publish from the team's authenticated AWS deployment environment

1. Use the existing ClearPath stack, account, us-east-1 region, AWS profile,
   and the exact CDK context/settings used for the current deployment.
2. Compile infrastructure and inspect `cdk diff`. The backend code asset should
   change. This patch adds no infrastructure resources or IAM permissions.
3. Deploy the API/worker Lambda asset with the existing deployment command and
   `--require-approval broadening`. Follow `aws-deployment-runbook.md`; do not
   recreate bootstrap, change model/domain/resource context, or activate Memory.
4. Build the frontend with the existing production API URL and Cognito settings.
   In PowerShell, use `$env:VITE_AUTH_MODE = "cognito"` and the existing values
   for `VITE_API_BASE_URL`, `VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID`,
   `VITE_COGNITO_REDIRECT_URI`, and `VITE_COGNITO_SCOPE` before building.
5. Publish `frontend/dist` to the existing website bucket and invalidate
   `/index.html` on the existing CloudFront distribution as in the runbook.
   Publish the backend first: the old backend rejects replacement even if the
   new frontend button is visible.

These actions update the shared site, even when run from an unmerged branch.
Commit/review a traceable version using the team's workflow before deployment.
No deployment was performed while preparing this patch because no AWS
credentials or deployment profile were available in this workspace.

## Verify the hosted site

Open https://d5ztmc348hleb.cloudfront.net/ after refreshing the page. Resume the
case containing the mistakenly uploaded resume, choose Client Profile, select
the correct fictional PDF, and click **Replace PDF**. Repeat for Transfer
Application and Account Statement as needed. The existing PDF remains current
until the upload is confirmed. Old findings clear on success; run Analyze packet
again. Failed transfers can be retried by selecting that type and uploading again.

With the original Packet B documents, verify policy version `sample-transfer-v2`,
missing DOB, missing signature date, account-type mismatch, and a low-severity
address formatting advisory. There should be no false statement name/address/
account-number findings. Partial/manual-review status is expected for the
account-type conflict. Verify source links open the replacement PDFs and review
accept/dismiss still works. Local tests mock the AWS upload boundary; live
Textract, S3, Guardrails, and Bedrock behavior still requires this hosted check.

Superseded S3 PDFs are retained; the patch removes them from the current packet
rather than adding delete permissions. It doesn't automatically classify resumes
or stop a reviewer from choosing the wrong document type in the future.
