from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["pgvector"]


async def test_health_reports_unreachable_db() -> None:
    app = create_app("postgresql+psycopg://tenet:tenet@127.0.0.1:1/tenet")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    await app.state.engine.dispose()

    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "error", "pgvector": None}
