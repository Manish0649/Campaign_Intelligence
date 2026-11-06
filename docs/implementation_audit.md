# Implementation Audit — Consolidated Update

## Implemented in this delivery

### Security and governance

- Added JWT login and verification with `sub`, `role`, `iat`, `exp`, `iss` and `aud` claims.
- Protected proposal, forecast, feasibility, decision and knowledge-base routers. Health and login remain public.
- Approval authority and actor identity are derived from the signed JWT; legacy body fields are only accepted for compatibility and must match the token.
- Added environment-backed multiple-account configuration through `AUTH_USERS_JSON`.
- Enforced role spending limits, creator/approver separation, approver/activator separation and activation role allowlisting.
- Added activation-time inventory and supplier revalidation.
- Changed approval and activation persistence to conditional SQL state transitions to prevent concurrent duplicate actions.
- Added persistent `fct_proposal_audit_events` for proposal creation, approval/rejection and activation. Events are written in the same transaction as the corresponding state change.
- Campaign status transitions to `active` with successful proposal activation.
- Added additive startup migration for the existing proposal table's `activated_at` field.
- Added public liveness (`/health`) and database readiness (`/health/ready`) endpoints; production API documentation endpoints are disabled.
- Added OpenAI API-key redaction to log sanitization and sanitized provider errors.
- Production startup requires a strong JWT secret and account configuration; API docs are disabled in production.

### Business rules and database

- Removed the domain-level assumed `$5.00` product price fallback. Missing or invalid registered prices now reject feasibility.
- Removed zero-demand fallback sell-price assumptions from cost calculations.
- Kept missing supplier evidence fail-closed and validates positive lead time, MOQ, capacity and replenishment timing.
- Added SQLAlchemy check constraints for prices, sales, inventory, supplier fields, campaign dates/budgets/discounts, cost assumptions and proposal states.
- Added a non-destructive Neon ingestion path using staging tables and primary-key upserts. Historical sample proposal CSV rows are not imported into the live proposal table because that file includes pre-approved sample records.
- Full truncation is only possible with the explicit `--replace-existing` flag; it remains destructive and must only be used after a backup.

### Forecasting and data quality

- Corrected rolling feature calculations so windows are isolated per product; one SKU's history cannot bleed into another SKU.
- Rolling features now require complete windows and the feature pipeline removes the warm-up rows before model training.
- Regenerated `data/processed/m5_processed_features.csv` and the 7-day forecast output from the updated feature pipeline.
- Added MAE, RMSE, WAPE and sMAPE. MAPE is retained as a non-zero-actual diagnostic only.
- Added processed-table checks for duplicate keys, invalid dates, negative values, bad prices, orphan product/campaign references and supplier readiness warnings.
- Current processed data audit: no structural errors; one supplier record is intentionally unavailable (suspended with missing lead time), and the report warns that campaigns relying on it must fail feasibility.

### Zilliz and RAG

- Replaced the destructive/legacy ingestion flow with deterministic Markdown chunk IDs and Zilliz upserts.
- Removed the fake hash-vector embedding fallback. Semantic retrieval requires a configured OpenAI embedding model and key.
- Existing collections are not dropped automatically. `--recreate` is explicit and destructive.
- Added protected `POST /knowledge-base/search` and a Streamlit Policy Knowledge Base page.
- Added optional advisory policy retrieval to LangGraph orchestration. Retrieval failure does not block deterministic planning and retrieved text cannot override SQL facts or feasibility constraints.

### Delivery and developer experience

- Added root README, `.env.example`, `.gitignore`, `.dockerignore`, Dockerfiles and Docker Compose configuration.
- Added focused tests for signed authentication, proposal lifecycle audit events, atomic activation, product-isolated rolling features, forecast metrics and knowledge-base chunking.
- Added updated forecasting, security and data-quality documentation.

## Validation performed in this workspace

- Python compilation: `python -m compileall -q backend frontend knowledge_base scripts tests` — passed.
- Focused isolated tests: **61 passed**. This run covered proposal API governance, audit persistence, authentication helpers, feasibility, inventory/replenishment, forecasting metrics, product-group feature boundaries and knowledge-base chunking.
- M5 feature pipeline: completed; 182,500 source rows became 165,500 modeling rows after warm-up removal.
- Forecast pipeline: completed; 10,500 forecast rows generated (500 products × 7 days × 3 models).
- Processed data-quality checks: `passed_with_warnings`; no structural errors, one intentionally suspended supplier warning.

## External validation not performed here

- The full repository test suite could not be run in this workspace because the environment did not have LangGraph and the Laya adapter package installed. Both are now declared in `backend/requirements.txt`; install the requirements and run the full suite locally.
- Live NeonDB migration/ingestion was not run. Review the target database and take a backup before using `scripts/load_to_neon.py`; `--replace-existing` is destructive.
- Live Zilliz/OpenAI ingestion and retrieval were not run because no external credentials were configured in this workspace.
- Docker images were authored but not built or started in this workspace.

## Remaining production hardening

- Move the environment-backed account map to a proper identity provider with password hashing, MFA and account lifecycle management.
- Add login rate limiting/lockout and token revocation/refresh policy.
- Introduce versioned Alembic migrations for future schema changes.
- Run rolling-origin forecast backtests before changing the configured production model.
- Validate live Zilliz schema compatibility, ingestion volume, latency and retrieval quality with the actual cluster.
- Add deployment-specific monitoring, backups, restore drills, TLS and secret-manager integration.
