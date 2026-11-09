import json
from pathlib import Path
from typing import Any

from app.github.signature import sign
from app.llm.gateway import RecordedGateway

FIXTURES = Path(__file__).parent / "fixtures"
WEBHOOK_SECRET = "test-webhook-secret"
REPO = "acme-pay/payments-service"
INSTALLATION_ID = 4242

PRS = {
    284: {
        "title": "Bounded automatic retries for transient payment failures",
        "author": "arjun-acme",
        "body": "Retries transient processor failures automatically.\n\nImplements: D-014",
        "sha": "a284" + "0" * 36,
    },
    291: {
        "title": "Retry transient payment failures automatically",
        "author": "tenet-coding-agent[bot]",
        "body": "Adds automatic retries for transient payment failures.\n\nImplements: D-014",
        "sha": "b291" + "0" * 36,
    },
}


class FakeGitHub:
    def __init__(self, diffs: dict[int, str] | None = None) -> None:
        self.diffs = diffs if diffs is not None else {n: diff_fixture(n) for n in PRS}
        self.check_runs: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []

    async def get_pull_diff(self, installation_id: int, repo: str, number: int) -> str:
        return self.diffs[number]

    async def create_check_run(
        self, installation_id: int, repo: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.check_runs.append({"installation_id": installation_id, "repo": repo, **payload})
        return {"id": len(self.check_runs)}

    async def create_comment(
        self, installation_id: int, repo: str, number: int, body: str
    ) -> dict[str, Any]:
        self.comments.append({"repo": repo, "number": number, "body": body})
        return {"id": len(self.comments)}


def diff_fixture(number: int) -> str:
    return (FIXTURES / "github" / f"pr_{number}.diff").read_text()


def recorded(**tasks: list[str]) -> RecordedGateway:
    return RecordedGateway.from_files(FIXTURES / "llm", tasks)


def pr_event(number: int, action: str = "opened", body: str | None = None) -> dict[str, Any]:
    pr = PRS[number]
    return {
        "action": action,
        "number": number,
        "installation": {"id": INSTALLATION_ID},
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": number,
            "title": pr["title"],
            "body": pr["body"] if body is None else body,
            "user": {"login": pr["author"]},
            "head": {"sha": pr["sha"]},
            "html_url": f"https://github.com/{REPO}/pull/{number}",
        },
    }


def signed(payload: dict[str, Any], event: str, delivery: str, secret: str = WEBHOOK_SECRET):
    body = json.dumps(payload).encode()
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": sign(secret, body),
        "Content-Type": "application/json",
    }
    return body, headers
