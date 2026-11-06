# Security and Governance Controls — Current Implementation

## Authentication

- `/auth/login` issues a signed JWT with `sub`, `role`, `iat`, `exp`, `iss` and `aud` claims.
- Protected business routers require a Bearer token. Health and login remain public.
- Approval authority is read from the signed JWT, not from `approver_role` or `approver_id` supplied in the JSON body.
- Activation authority is also derived from the token. The body cannot claim another activator identity.
- Production startup rejects missing/weak JWT secrets and missing account configuration.
- Multiple accounts and roles can be configured with `AUTH_USERS_JSON`; use separate accounts for approvers and operations users.

## Approval and activation governance

- Approval roles are checked against the spending-authority matrix in `backend/app/api/routes/proposals.py`.
- Approval and activation require a proposal in the correct state.
- The proposal creator cannot approve their own proposal.
- The approver cannot activate the same proposal (four-eyes control).
- Approval revalidates inventory and supplier readiness.
- Activation revalidates inventory and supplier readiness again immediately before launch.
- Repository state transitions use conditional SQL updates so concurrent requests cannot both approve/activate a proposal.
- Duplicate activation returns HTTP 409.

## Persistent audit trail

`fct_proposal_audit_events` records `proposal_created`, `proposal_approved`, `proposal_rejected` and `proposal_activated` events with actor ID, authenticated role, timestamp and event details. Events are committed in the same transaction as the corresponding proposal state transition. Protected endpoint: `GET /campaigns/proposals/{proposal_id}/audit`.

## Secret handling and deployment

- `.env` is excluded from the delivered archive and Git by `.gitignore`.
- `.env.example` contains placeholders only.
- CORS origins are configurable with `CORS_ALLOWED_ORIGINS`; wildcard origins with credentials are not enabled.
- Zilliz ingestion does not log credentials and never falls back to fake hash vectors.
- Rotate any real credentials that were included in an earlier shared ZIP.

## Remaining production hardening

- Replace the simple environment-backed account map with an enterprise identity provider / password hashing and account lifecycle management before public production deployment.
- Add rate limiting and login lockout.
- Add database migration tooling (e.g. Alembic) for versioned schema evolution.
- Add an external immutable audit sink if regulatory-grade tamper resistance is required.
- Validate TLS, secret manager integration, backup/restore and deployment-specific network policies.
