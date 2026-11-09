"""Who may do what: one permission matrix.

Space actions depend on the caller's role in that space. Org actions depend on being an org admin
or an external guest. Space admins and org admins can manage a space's members; nobody gets a
space's content without a role in it (org admins included: privacy beats hierarchy).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member, Space, User
from app.review import Forbidden

READ = ("admin", "owner", "member", "viewer", "guest")
WRITE = ("admin", "owner", "member")

SPACE_ACTIONS: dict[str, tuple[str, ...]] = {
    "space.read": READ,
    "ask": READ,
    "item.add": WRITE,
    "doc.sync": READ,
    "proposal.create": WRITE,
    "proposal.review": WRITE,  # the stage owner check happens in review.py
    "pushback.raise": WRITE,
    "finding.share": WRITE,
    "finding.reply": WRITE,
    "finding.promote": WRITE,
    "member.manage": ("admin",),
}
# Org actions: None = any internal member; "admin" = org admins only.
ORG_ACTIONS: dict[str, str | None] = {
    "space.create": None,
    "org.directory": None,  # list the org's people
    "org.admin": "admin",
    "member.invite": "admin",
    "domain.manage": "admin",
    "audit.read": "admin",
    "usage.read": "admin",
}


async def space_role(session: AsyncSession, space: Space, user: User) -> str | None:
    return await session.scalar(
        select(Member.role).where(Member.space_id == space.id, Member.user_id == user.id)
    )


def org_allows(user: User, action: str) -> bool:
    need = ORG_ACTIONS[action]
    if not user.active or user.external:
        return False
    return need is None or user.is_org_admin


async def allowed(
    session: AsyncSession, user: User, action: str, space: Space | None = None
) -> bool:
    if action in ORG_ACTIONS:
        return org_allows(user, action)
    if space is None or space.org_id != user.org_id or not user.active:
        return False
    role = await space_role(session, space, user)
    if action == "member.manage" and user.is_org_admin and not user.external:
        return True
    return role in SPACE_ACTIONS[action]


async def require(
    session: AsyncSession, user: User, action: str, space: Space | None = None
) -> str | None:
    """Raise Forbidden unless the matrix allows it. Returns the caller's role in the space."""
    if await allowed(session, user, action, space):
        return await space_role(session, space, user) if space is not None else None
    if action in ORG_ACTIONS:
        if user.external:
            raise Forbidden("external guests can only work in the spaces they're invited to")
        raise Forbidden("only an org admin can do this")
    role = await space_role(session, space, user) if space is not None else None
    handle = f"@{space.handle}" if space is not None else "this space"
    if role is None:
        raise Forbidden(f"{user.name} is not a member of {handle}")
    raise Forbidden(f"{user.name} is a {role} in {handle} and can't do this")
