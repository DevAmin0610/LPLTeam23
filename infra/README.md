# ClearPath infrastructure draft

Undeployed TypeScript CDK definitions. **Do not deploy or bootstrap this starter.** The backend Lambda handlers and AWS composition are not implemented; packaging intentionally checks for them.

```sh
npm ci
npm run build
```

`npm run synth` is reserved for after backend wiring and workshop approval. It uses no account lookups but packages Python dependencies (Docker/network needed); `synth:local` uses the local Python packager. No live synthesis or resource creation is needed for local demo development.

Context keys in `lib/clearpath-stack.ts`: `existingBucketName`, `existingTableName`, `guardrailId` plus published `guardrailVersion`, `modelId`, `additionalModelArns`, `frontendOrigins`, `apiFunctionName`, `workerFunctionName`, `localBundling`, `allowUnauthenticatedApi`. Existing tables must have string partition key `id`. Existing bucket encryption/CORS/public access settings are not altered by imports; organizers must verify them. Use full inference-profile ARNs and exact destination model ARNs for scoped IAM. The default model identifier is only a draft, not a workshop availability guarantee.

The API defaults to IAM authorization, not a complete advisor authentication flow. Do not turn on unauthenticated public access. Add case authorization in the backend. Review permission-boundary support and existing worker/API integration with organizers before any deployment. Resource names/context are not permission to create replacements.

See `../docs/handoff.md` and `../docs/aws-connection-checklist.md`.
