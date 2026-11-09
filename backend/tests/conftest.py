from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings, get_settings
from app.db import make_engine, make_sessionmaker
from app.main import create_app
from app.seed import SeedResult, seed
from tests.fakes import WEBHOOK_SECRET

BACKEND_DIR = Path(__file__).resolve().parents[1]


def libpq_url(sqlalchemy_url: str) -> str:
    """postgresql+psycopg://... -> postgresql://... for direct psycopg connections."""
    url = make_url(sqlalchemy_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = get_settings().test_database_url
    try:
        psycopg.connect(libpq_url(url), connect_timeout=2).close()
    except psycopg.OperationalError as exc:
        pytest.skip(f"test database unreachable; run `docker compose up -d --wait db` ({exc})")
    return url


@pytest.fixture(scope="session")
def alembic_config(test_database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_db(alembic_config: Config) -> Iterator[None]:
    command.upgrade(alembic_config, "head")
    yield
    command.downgrade(alembic_config, "base")


@pytest.fixture
def db_conn(test_database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(libpq_url(test_database_url), autocommit=True) as conn:
        yield conn


@pytest.fixture
async def engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back after the test; commits become savepoints."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
def fresh_db(alembic_config: Config) -> Iterator[None]:
    """An empty schema for tests that commit (webhooks, background work); reset again after."""
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    yield
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


@pytest.fixture
async def seeded_v4(fresh_db: None, engine: AsyncEngine) -> SeedResult:
    """@payments-redesign seeded through v4 (D-014 approved) and committed."""
    async with make_sessionmaker(engine)() as session, session.begin():
        return await seed(session, through=4)


@pytest.fixture
async def seeded_v3(fresh_db: None, engine: AsyncEngine) -> SeedResult:
    async with make_sessionmaker(engine)() as session, session.begin():
        return await seed(session, through=3)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        github_webhook_secret=WEBHOOK_SECRET,
        anthropic_api_key=None,
        slack_bot_token=None,
        web_url="http://web.test",
    )


@pytest.fixture(scope="session")
def test_api_database_url(test_database_url: str) -> str:
    """The app connects as the least-privileged tenet_api role, as in production, so row-level
    security binds every test that goes through the API."""
    return get_settings().test_api_database_url


@pytest.fixture
def app_factory(test_api_database_url: str, test_settings: Settings):
    """Build an app with fakes; returns (app, AsyncClient) via an async context manager."""
    apps: list[FastAPI] = []

    @asynccontextmanager
    async def build(**services: Any) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
        services.setdefault("github", None)
        services.setdefault("llm", None)
        services.setdefault("notifier", None)
        services.setdefault("drive", None)
        services.setdefault("background_sync", False)
        app = create_app(test_api_database_url, settings=test_settings, **services)
        apps.append(app)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield app, client
        await app.state.engine.dispose()

    return build


@pytest.fixture
async def client(test_api_database_url: str) -> AsyncIterator[AsyncClient]:
    app = create_app(test_api_database_url)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await app.state.engine.dispose()
