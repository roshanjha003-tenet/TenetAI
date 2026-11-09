"""Load the demo PR checks (#284 passes, #291 drifts) into the dev database.

Delivers both pull_request webhooks through the real app, with the recorded model responses and
diffs from the test fixtures, so the web UI has PR checks and PR agents to show without a GitHub
App or an Anthropic key. Run after `python -m app.seed --reset --through 4`.

    uv run python scripts/load_demo_prs.py
"""

import asyncio
import sys
from pathlib import Path

from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.fakes import WEBHOOK_SECRET, FakeGitHub, pr_event, recorded, signed  # noqa: E402


async def main() -> None:
    settings = get_settings().model_copy(update={"github_webhook_secret": WEBHOOK_SECRET})
    llm = recorded(
        pr_analyzer=["pr_284_analyzer.json", "pr_291_analyzer.json"],
        pr_evaluator=["pr_291_evaluator.json"],
    )
    github = FakeGitHub()
    app = create_app(
        settings=settings, github=github, llm=llm, notifier=None, drive=None, background_sync=False
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as client:
        for number in (284, 291):
            body, headers = signed(pr_event(number), "pull_request", f"demo-{number}")
            response = await client.post("/webhooks/github", content=body, headers=headers)
            print(f"PR #{number}: {response.json()['status']}")
    await app.state.engine.dispose()
    for run in github.check_runs:
        print(f"  {run['conclusion']:8} {run['output']['title']}")


if __name__ == "__main__":
    asyncio.run(main())
