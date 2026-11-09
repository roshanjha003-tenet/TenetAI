"""Google Drive: private session attachments, per-person connector tokens, synced items

Attachments and tokens follow the private-session rules: row-level security to their owner for
tenet_app, and no access at all for tenet_agent.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIVATE = ("session_attachments", "connector_tokens")
OWNER_IS_USER = "owner_id = nullif(current_setting('tenet.user_id', true), '')::uuid"


def upgrade() -> None:
    op.add_column("items", sa.Column("source_id", sa.String(length=200), nullable=True))
    op.add_column("items", sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "session_attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("shared_item_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["private_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_attachments_session_id", "session_attachments", ["session_id"])
    op.create_table(
        "connector_tokens",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("owner_id", "provider"),
    )
    for table in PRIVATE:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO tenet_app")
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
    op.drop_table("connector_tokens")
    op.drop_index("ix_session_attachments_session_id", table_name="session_attachments")
    op.drop_table("session_attachments")
    op.drop_column("items", "synced_at")
    op.drop_column("items", "source_id")
