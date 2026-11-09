import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Area, Org, Space, User


async def make_space(session: AsyncSession) -> tuple[Space, User, Area]:
    """A bare space (HEAD 0) with one user who owns its one area."""
    suffix = uuid.uuid4().hex[:8]
    org = Org(name=f"Org {suffix}")
    session.add(org)
    await session.flush()
    user = User(org_id=org.id, email=f"owner-{suffix}@example.test", name=f"Owner {suffix}")
    session.add(user)
    await session.flush()
    space = Space(org_id=org.id, handle=f"space-{suffix}", name="Test space", created_by=user.id)
    session.add(space)
    await session.flush()
    area = Area(space_id=space.id, key="core", name="Core", owner_id=user.id)
    session.add(area)
    await session.flush()
    return space, user, area
