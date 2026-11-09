import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def vector_version(conn: psycopg.Connection) -> str | None:
    row = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
    return row[0] if row else None


def test_vector_extension_installed(db_conn: psycopg.Connection) -> None:
    assert vector_version(db_conn)


def test_vector_column_round_trips(db_conn: psycopg.Connection) -> None:
    db_conn.execute("CREATE TEMP TABLE embeddings (embedding vector(3))")
    db_conn.execute("INSERT INTO embeddings VALUES ('[1,2,3]')")

    row = db_conn.execute("SELECT embedding::text FROM embeddings").fetchone()

    assert row == ("[1,2,3]",)


def test_downgrade_then_upgrade(alembic_config: Config, db_conn: psycopg.Connection) -> None:
    command.downgrade(alembic_config, "base")
    assert vector_version(db_conn) is None

    command.upgrade(alembic_config, "head")
    assert vector_version(db_conn)
    head = ScriptDirectory.from_config(alembic_config).get_current_head()
    assert db_conn.execute("SELECT version_num FROM alembic_version").fetchone() == (head,)
