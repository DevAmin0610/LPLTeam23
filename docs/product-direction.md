# ClearPath product direction: reviewer-informed document review

## Purpose

ClearPath is an independent, local-first hackathon prototype for reviewing document packets: identify missing information and discrepancies, explain findings, and let a human reviewer accept or dismiss findings and record rationale. Use synthetic documents and explicitly fictional policies only. This is not official LPL policy, an LPL-endorsed product, or a regulatory compliance guarantee.

The intended differentiator is a feedback loop that turns **validated reviewer rationale into reusable institutional knowledge**. A foundation model can reason over supplied context, but does not automatically know an organization's workflows or historical mistakes. Relevant, approved lessons from prior reviews could improve explanations and suggested next steps without fine-tuning the model.

Suggested pitch:

> ClearPath turns validated reviewer feedback into reusable institutional knowledge, helping future reviews recognize recurring issues and suggest better next steps—without retraining the foundation model.

## Implemented versus planned

**Implemented local starter:** PDF extraction for supported synthetic fixtures, deterministic sample rules and explanations, case/job persistence in SQLite, local document storage, findings, accept/dismiss decisions, optional review notes, and a correction checklist. See `README.md` and `docs/handoff.md` for limitations.

**Implemented proof of concept:** reviewers can explicitly mark a decision `remember`; the application stores only its privacy-safe pattern and status in authoritative review memory. When configured with a Memory and semantic strategy ID, the AgentCore adapter ingests fixed lesson text that excludes reviewer notes and source values, and retrieved advisory lessons can inform later explanations without changing findings.

**Not implemented:** structured review reasons, role-based lesson approval, tenant-scoped memory, complete AgentCore provenance/revocation, or memory provenance in the UI. Existing review notes are not privacy-filtered and must not be sent directly to a model or memory service. Accepting a finding does not prove a correction was completed; dismissing one does not establish a reusable exception.

**AWS status:** the stack is deployed in account `033890317696`, `us-east-1`, with CloudFormation status `UPDATE_COMPLETE`. Cognito sign-in, JWT-protected frontend/API connectivity, CORS preflight handling, and unauthenticated `401` behavior are verified. AgentCore Memory is provisioned, but no runtime strategy ID is configured, so AgentCore ingestion/retrieval is inactive. DynamoDB remains authoritative for approval eligibility. The complete AWS upload/analyze/review workflow has not yet been validated. This direction does not authorize further deployment, bootstrapping, IAM changes, resource creation, or runtime activation.

## Proposed feedback loop

1. Analyze a synthetic document packet using versioned rules and sanitized context.
2. A human reviews the findings and supplies a structured reason and supporting rationale.
3. Create a candidate lesson from a validated review outcome; do not treat every user statement or model output as established knowledge.
4. Apply privacy filtering and require explicit approval by an authorized reviewer before ingesting a reusable lesson into memory.
5. Retrieve relevant approved lessons for a later, similar case, within the allowed organizational and case-access scope.
6. Use those lessons to improve explanations and suggested next steps, showing their provenance and applicability. Keep deterministic findings and human review decisions intact.

For example, in a **fictional sample workflow**, an address discrepancy may involve mailing versus residential address fields. An approved lesson could suggest checking field semantics before recommending a correction. It must not silently suppress the discrepancy, declare the case compliant, or create an exception to policy.

## Knowledge boundaries

| Layer                                                                                          | Responsibility                                                             | Authority                                                           |
| ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Case records: SQLite locally; S3/DynamoDB provisioned for AWS, full workflow not yet validated | Source documents, case/job state, findings, review decisions and rationale | Evidence and recorded events for a specific case                    |
| Versioned rules and approved policy sources                                                    | Explicit business requirements and deterministic checks                    | What the application must enforce                                   |
| AgentCore Memory: resource provisioned; runtime integration inactive                           | Sanitized, approved lessons retrieved from prior reviews                   | Advisory context, never a replacement for policy or source evidence |

A newer memory must not override an approved rule merely because it is newer. Conflicts require review. Maintain approval, provenance, scope, applicable policy/rule version, and revocation records in the authoritative application store rather than relying on model-generated summaries as an audit record. Recheck lesson eligibility when retrieving it.

## AgentCore design guidance

The team received a workshop recommendation to investigate **Amazon Bedrock AgentCore Memory**, particularly semantic memory extraction and consolidation. This is more than generic chat history: the proposed value is remembering validated resolution patterns across reviews.

- Memory extraction, consolidation, and retrieval supply context; they do not fine-tune model weights or guarantee continuous improvement.
- AgentCore Memory does not inherently provide a business ontology or knowledge graph. A graph is a separate design decision; do not add one without a concrete requirement.
- AgentCore Runtime and AgentCore Memory are separate choices. Memory can be called from an application hosted elsewhere, including Lambda. Do not replace the existing execution architecture solely to add memory.
- Extraction is asynchronous. Persist the review synchronously in the application store, expose pending/failed lesson processing honestly, and do not assume immediate retrieval after ingestion.
- A memory-service failure must never fabricate a lesson or substitute demo output. Whether an AWS analysis may continue without optional memory must be explicitly designed and tested; privacy failures always stop the affected model/memory invocation.
- Confirm workshop permissions, availability, cost, and all processing/model region constraints before changing Memory configuration or activating runtime ingestion/retrieval. Provisioning alone does not establish that semantic processing is permitted or active. The team's workshop restriction is **us-east-1 only**; do not assume cross-region inference is allowed.

Background: [AWS: Building smarter AI agents—AgentCore long-term memory deep dive](https://aws.amazon.com/jp/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/). The article describes semantic, preference, and summary strategies, extraction/consolidation, and retrieval trade-offs. Its benchmarks do not establish ClearPath accuracy or business outcomes.

## Privacy and trust requirements

- Sanitize and validate content **before memory ingestion**: extraction and consolidation may themselves invoke models. Filtering only the final explanation is insufficient.
- Never ingest raw documents, source identifiers, secrets, or unfiltered case names/review notes. Use synthetic data throughout this prototype.
- Treat review text and retrieved memories as untrusted data, not instructions. Prevent user input or model-generated suggestions from promoting themselves into approved knowledge.
- Separate case-specific context from deliberately approved, generalized organizational lessons. Enforce authorization server-side; namespaces are useful organization but not an authorization boundary on their own.
- Define retention, deletion, revocation, and stale-policy handling before shared use. Do not carry one client's details into another case.
- Memory may inform explanations and next steps in the initial proof of concept, not modify deterministic rules, approve cases, or waive findings.

## Smallest useful proof of concept

Demonstrate one approved, sanitized lesson from a synthetic review influencing the explanation for a second similar synthetic case. Show the before/after explanation and the lesson's source, while preserving the underlying finding. Include irrelevant, conflicting, revoked, privacy-blocked, and unavailable-memory cases in validation.

Compare the same cases with and without memory. Measure explanation/action usefulness and correctness, inappropriate lesson reuse, privacy leakage, latency, and cost. Do not claim that six months of use fixes 99% of mistakes, that memory guarantees compliance, or that accuracy improved without a measured evaluation.

Implementation should be explicitly scoped before editing runtime code. Coordinate new review/lesson contracts across Python schemas, TypeScript types, and `docs/api-contract.md`; keep business and approval rules in shared services. Preserve a credential-free, network-free demo mode. Any simulated memory behavior must be labeled as simulated, never presented as a live AgentCore integration.
