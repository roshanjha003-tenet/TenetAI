"""Private sessions with row-level security, and the database roles that enforce privacy

Two roles, assumed with SET LOCAL ROLE inside a transaction:
- tenet_app: sees a private session row only when tenet.user_id is that row's owner.
- tenet_agent: used for every agent code path; it has no access to private tables at all.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIVATE = ("private_sessions", "private_messages")
OWNER_IS_USER = "owner_id = nullif(current_setting('tenet.user_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tenet_app') THEN
                CREATE ROLE tenet_app NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tenet_agent') THEN
                CREATE ROLE tenet_agent NOLOGIN;
            END IF;
        END
        $$
        """
    )
    op.create_table(
        "private_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_private_sessions_owner_id", "private_sessions", ["owner_id"])
    op.create_table(
        "private_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("shared_event_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="role_allowed"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["private_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_private_messages_session_id", "private_messages", ["session_id"])

    # Both roles may use the shared tables; only tenet_app may touch private ones.
    for role in ("tenet_app", "tenet_agent"):
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {role}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
        op.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE ON TABLES TO {role}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}"
        )
    for table in PRIVATE:
        op.execute(f"REVOKE ALL ON {table} FROM tenet_agent")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} TO tenet_app "
            f"USING ({OWNER_IS_USER}) WITH CHECK ({OWNER_IS_USER})"
        )


def downgrade() -> None:
    for table in PRIVATE:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
    op.drop_index("ix_private_messages_session_id", table_name="private_messages")
    op.drop_table("private_messages")
    op.drop_index("ix_private_sessions_owner_id", table_name="private_sessions")
    op.drop_table("private_sessions")
    for role in ("tenet_app", "tenet_agent"):
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role}")
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
    # The roles are cluster-wide (shared by the dev and test databases), so they stay.
