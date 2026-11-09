import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import hardening
from app.access import dns_txt as dns_txt_lookup
from app.config import Settings, get_settings
from app.db import make_engine, make_sessionmaker
from app.github.client import GitHubAPI, make_github
from app.hardening import config_problems, database_problems
from app.llm.gateway import LLMGateway, make_gateway
from app.llm.metering import MeteredGateway
from app.oidc import make_oidc

UNSET: Any = object()


def create_app(
    database_url: str | None = None,
    *,
    settings: Settings | None = None,
    github: GitHubAPI | None = UNSET,
    llm: LLMGateway | None = UNSET,
    notifier: Any = UNSET,
    drive: Any = UNSET,
    oidc: Any = UNSET,
    dns_txt: Any = UNSET,
    background_sync: bool = True,
) -> FastAPI:
    """Build the app. Tests pass fakes for github, llm, notifier and drive; None turns a service
    off."""
    settings = settings or get_settings()
    engine = make_engine(database_url or settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        problems = config_problems(settings) + await database_problems(engine, settings)
        if problems:
            raise RuntimeError("refusing to start outside dev: " + "; ".join(problems))
        task = None
        if background_sync and app.state.drive is not None and settings.drive_sync_minutes > 0:
            from app.connectors.drive_items import sync_forever

            task = asyncio.create_task(sync_forever(app.state, settings.drive_sync_minutes))
        yield
        if task is not None:
            task.cancel()
        await engine.dispose()

    app = FastAPI(title="Tenet", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_url],
        allow_credentials=True,  # the session cookie
        allow_methods=["*"],
        allow_headers=["*"],
    )
    hardening.install(app, settings)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.github = make_github(settings) if github is UNSET else github
    llm = make_gateway(settings) if llm is UNSET else llm
    app.state.llm = MeteredGateway(llm, app.state.sessionmaker) if llm is not None else None
    app.state.oidc = make_oidc(settings) if oidc is UNSET else oidc
    app.state.dns_txt = dns_txt_lookup if dns_txt is UNSET else dns_txt
    if drive is UNSET:
        from app.connectors.google_drive import make_drive

        drive = make_drive(settings)
    app.state.drive = drive if drive is not None and drive.configured else None
    if notifier is UNSET:
        from app.notify.slack import make_notifier

        notifier = make_notifier(settings)
    app.state.notifier = notifier

    @app.get("/health")
    async def health(request: Request, response: Response) -> dict[str, str | None]:
        try:
            async with request.app.state.engine.connect() as conn:
                pgvector = await conn.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
        except (SQLAlchemyError, OSError):
            response.status_code = 503
            return {"status": "error", "db": "error", "pgvector": None}
        if pgvector is None:
            # Database is up but migrations haven't run.
            response.status_code = 503
            return {"status": "error", "db": "ok", "pgvector": None}
        return {"status": "ok", "db": "ok", "pgvector": pgvector}

    from app.api import admin as admin_routes
    from app.api import auth as auth_routes
    from app.api import connectors as connector_routes
    from app.api import findings as finding_routes
    from app.api import github as github_routes
    from app.api import private as private_routes
    from app.api import spaces as space_routes

    app.include_router(github_routes.router)
    app.include_router(space_routes.router, prefix="/api")
    app.include_router(private_routes.router, prefix="/api")
    app.include_router(finding_routes.router, prefix="/api")
    app.include_router(connector_routes.router, prefix="/api")
    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(admin_routes.router, prefix="/api")
    space_routes.install_error_handlers(app)
    return app


app = create_app()
