"""Small, non-destructive compatibility migrations for existing deployments.

For long-lived production environments, migrate this logic into Alembic
revisions. These guarded statements are intentionally additive only.
"""
from sqlalchemy import text


def run_compatibility_migrations(engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE fct_campaign_proposals ADD COLUMN IF NOT EXISTS activated_at TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS idx_proposal_audit_proposal_created ON fct_proposal_audit_events (proposal_id, created_at)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
