# Packet B findings regression

The fictional `sample-transfer-v2` policy requires Date of Birth, Signature Date,
and Account Type on transfer applications. Account Type is also extracted from
profiles and statements and compared deterministically. Optional labeled fields
are now extracted and validated even when they are not mandatory.

Source Account Number and Receiving Account Number remain separate. The sample
policy supports applications that supply only a receiving account; it no longer
asserts that a source account number must appear on every application. When a
source account number is supplied, it is still validated and compared to the
statement. A receiving number is never substituted into that source comparison.
This is a fictional workflow choice, not a statement of real transfer policy.

Packet B now yields three actionable findings: blank application DOB, blank
signature date, and Traditional IRA versus Roth IRA. It also yields one existing
address formatting advisory, now low severity: Lane/Ln and Apt/Unit normalize to
the same address. Formatting advisories still require human review and preserve
the current review-memory demo. The name's omitted middle initial does not create
a finding; name matching is not implemented by this patch.

The latest repository already recognizes Account Holder and Mailing Address and
accepts the statement's synthetic account-number format. Those fixes must be in
the running backend for the older screenshot's false missing/unreadable findings
to disappear. No deployed AWS state was changed.

Tests cover the actual uploaded PDFs, structured Textract-style fields with line
fallback, account-type matching/mismatch, low-confidence review, and the local
HTTP upload/analyze/privacy-preview path. The account-type conflict uses the
existing review-required category, so the job ends in partial/manual-review
status rather than an all-clear. Existing demo fixtures are regenerated
with the new required fields. Run `npm run test:backend` after installing the
backend development dependencies. Restart the backend and analyze a new case
with all three PDFs to see the new findings. Existing stored results are not
retroactively rewritten. Use the existing deployment runbook for an authorized
AWS backend update; this patch does not deploy or change IAM.
