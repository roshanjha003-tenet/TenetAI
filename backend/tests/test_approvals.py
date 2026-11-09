from tests.test_review import D014_BODY, as_


async def test_approvals_follow_the_current_stage(seeded_v3, app_factory) -> None:
    async with app_factory() as (_, client):
        pid = (
            await client.post(
                "/api/spaces/payments-redesign/proposals", json=D014_BODY, headers=as_("yashwant")
            )
        ).json()["id"]
        maya_before = (await client.get("/api/approvals", headers=as_("maya"))).json()
        arjun_before = (await client.get("/api/approvals", headers=as_("arjun"))).json()
        await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("maya"))
        maya_after = (await client.get("/api/approvals", headers=as_("maya"))).json()
        arjun_after = (await client.get("/api/approvals", headers=as_("arjun"))).json()

    assert [p["id"] for p in maya_before] == [pid]
    assert maya_before[0]["space"]["handle"] == "payments-redesign"
    assert arjun_before == []
    assert maya_after == []
    assert [p["id"] for p in arjun_after] == [pid]
