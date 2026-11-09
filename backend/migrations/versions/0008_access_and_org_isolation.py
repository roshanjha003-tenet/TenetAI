"""Access: sign-in sessions, audit log, domains, invites, metering; org isolation in the database

- New tables: auth_sessions, audit_log (append-only), org_domains, invites, usage_records.
- tenet_api: the least-privileged LOGIN role the API connects as. It is a member of tenet_app and
  tenet_agent, owns nothing, and so is bound by row-level security everywhere.
- Every org-scoped table gets a policy: rows are visible only when they belong to the org named in
  the transaction's `tenet.org_id` setting (set by the app for each request, webhook or job).
  Tables keyed by space_id follow their space; spaces follow their org.
- The few lookups that must happen before the org is known (who owns this session cookie, which
  org owns this repo, ...) are SECURITY DEFINER functions that return only an org id.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "nullif(current_setting('tenet.org_id', true), '')::uuid"

# table -> the condition that puts a row in the current org
ORG_SCOPED = {
    "orgs": f"id = {ORG}",
    "users": f"org_id = {ORG}",
    "spaces": f"org_id = {ORG}",
    "org_domains": f"org_id = {ORG}",
    "invites": f"org_id = {ORG}",
    "auth_sessions": "user_id IN (SELECT id FROM users)",
    "areas": "space_id IN (SELECT id FROM spaces)",
    "members": "space_id IN (SELECT id FROM spaces)",
    "items": "space_id IN (SELECT id FROM spaces)",
    "events": "space_id IN (SELECT id FROM spaces)",
    "state_versions": "space_id IN (SELECT id FROM spaces)",
    "decisions": "space_id IN (SELECT id FROM spaces)",
    "proposals": "space_id IN (SELECT id FROM spaces)",
    "branches": "space_id IN (SELECT id FROM spaces)",
    "pr_links": "space_id IN (SELECT id FROM spaces)",
    "pr_checks": "space_id IN (SELECT id FROM spaces)",
    "repos": "space_id IN (SELECT id FROM spaces)",
    "steward_jobs": "space_id IN (SELECT id FROM spaces)",
    "findings": "space_id IN (SELECT id FROM spaces)",
    "decision_revisions": "decision_id IN (SELECT id FROM decisions)",
    "proposal_reviews": "proposal_id IN (SELECT id FROM proposals)",
    "pushbacks": "proposal_id IN (SELECT id FROM proposals)",
    "finding_replies": "finding_id IN (SELECT id FROM findings)",
}
# Written before or without a signed-in org (failed sign-ins, unattributed calls): anyone may
# insert a row with no org, but reading needs the org. The app inserts these without RETURNING,
# since a returned row must also pass the read policy.
INSERT_WITHOUT_ORG = ("audit_log", "usage_records")

# name(args) -> body; each returns only an org id (or a set of them)
LOOKUPS = {
    "tenet_session_org(p_hash text)": """
        SELECT u.org_id FROM auth_sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = p_hash AND s.revoked_at IS NULL AND u.active""",
    "tenet_token_org(p_token text)": """
        SELECT org_id FROM users WHERE api_token = p_token AND active""",
    "tenet_email_org(p_email text)": """
        SELECT org_id FROM users WHERE lower(email) = lower(p_email)""",
    "tenet_domain_org(p_domain text)": """
        SELECT org_id FROM org_domains
        WHERE domain = lower(p_domain) AND verified_at IS NOT NULL""",
    "tenet_invite_org(p_hash text)": """
        SELECT org_id FROM invites WHERE token_hash = p_hash""",
    "tenet_repo_org(p_repo text)": """
        SELECT s.org_id FROM repos r JOIN spaces s ON s.id = r.space_id
        WHERE r.full_name = p_repo""",
    "tenet_user_org(p_user uuid)": """
        SELECT org_id FROM users WHERE id = p_user""",
}


def upgrade() -> None:
    op.add_column(
        "orgs", sa.Column("monthly_cap_usd", sa.Numeric(precision=10, scale=2), nullable=True)
    )
    op.execute("UPDATE orgs SET monthly_cap_usd = 50")
    for column, default in (("active", "true"), ("is_org_admin", "false"), ("external", "false")):
        op.add_column(
            "users", sa.Column(column, sa.Boolean(), server_default=default, nullable=False)
        )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("subject", sa.String(length=320), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("outcome IN ('success', 'failure')", name="outcome_allowed"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq"),
    )
    op.create_index("ix_audit_log_org_id", "audit_log", ["org_id"])
    op.execute(
        "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION forbid_change()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_change()"
    )
    op.create_table(
        "org_domains",
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("verification_token", sa.String(length=64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("domain"),
    )
    op.create_index("ix_org_domains_org_id", "org_domains", ["org_id"])
    op.create_table(
        "invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_org_id", "invites", ["org_id"])
    op.create_table(
        "usage_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=True),
        sa.Column("task", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_records_org_id", "usage_records", ["org_id"])

    # The API's login role. Set a real password outside dev: ALTER ROLE tenet_api PASSWORD '...'.
    password = os.environ.get("TENET_API_PASSWORD", "tenet_api").replace("'", "''")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tenet_api') THEN
                CREATE ROLE tenet_api LOGIN PASSWORD '{password}';
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT tenet_app, tenet_agent TO tenet_api")
    op.execute("REVOKE UPDATE ON audit_log FROM tenet_app, tenet_agent")

    for table, condition in ORG_SCOPED.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_org ON {table} USING ({condition})")
    for table in INSERT_WITHOUT_ORG:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_org_read ON {table} FOR SELECT USING (org_id = {ORG})")
        op.execute(
            f"CREATE POLICY {table}_org_write ON {table} FOR INSERT "
            f"WITH CHECK (org_id IS NULL OR org_id = {ORG})"
        )

    for signature, body in LOOKUPS.items():
        op.execute(
            f"CREATE FUNCTION {signature} RETURNS uuid LANGUAGE sql STABLE "
            f"SECURITY DEFINER SET search_path = public AS $$ {body} LIMIT 1 $$"
        )
        name = signature.split("(")[0]
        args = signature[signature.index("(") + 1 : -1].split(" ", 1)[1]
        op.execute(f"REVOKE ALL ON FUNCTION {name}({args}) FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {name}({args}) TO tenet_app, tenet_agent")
    op.execute(
        "CREATE FUNCTION tenet_orgs() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER "
        "SET search_path = public AS $$ SELECT id FROM orgs $$"
    )
    op.execute("REVOKE ALL ON FUNCTION tenet_orgs() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION tenet_orgs() TO tenet_app, tenet_agent")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS tenet_orgs()")
    for signature in LOOKUPS:
        name = signature.split("(")[0]
        args = signature[signature.index("(") + 1 : -1].split(" ", 1)[1]
        op.execute(f"DROP FUNCTION IF EXISTS {name}({args})")
    for table in ORG_SCOPED:
        op.execute(f"DROP POLICY IF EXISTS {table}_org ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE tenet_app, tenet_agent FROM tenet_api")
    # tenet_api is cluster-wide (shared by the dev and test databases), so it stays.

    op.drop_index("ix_usage_records_org_id", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index("ix_invites_org_id", table_name="invites")
    op.drop_index("ix_invites_email", table_name="invites")
    op.drop_table("invites")
    op.drop_index("ix_org_domains_org_id", table_name="org_domains")
    op.drop_table("org_domains")
    op.drop_index("ix_audit_log_org_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    for column in ("external", "is_org_admin", "active"):
        op.drop_column("users", column)
    op.drop_column("orgs", "monthly_cap_usd")
