## 1. TWSE Client

- [x] 1.1 Add failing tests for TWSE OpenAPI dataset fetch and listed-company row mapping
- [x] 1.2 Implement the TWSE OpenAPI client and Taiwan issuer normalization helpers

## 2. Taiwan Snapshot Storage

- [x] 2.1 Add failing tests for persisting Taiwan monthly and quarterly snapshots into the shared financial report store
- [x] 2.2 Implement Taiwan financial snapshot persistence with provenance and confidence metadata

## 3. Report Orchestration

- [x] 3.1 Add failing tests for bounded Taiwan issuer refresh during report runs
- [x] 3.2 Integrate Taiwan financial refresh into the main report flow

## 4. Financial Augmentation

- [x] 4.1 Add failing tests for Taiwan financial context augmentation in summary and memo prompts
- [x] 4.2 Reuse the financial augmentation path for Taiwan issuer snapshots
