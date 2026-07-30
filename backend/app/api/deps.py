"""Request-scoped dependencies.

`current_user` is the gate every case-data route sits behind. It verifies the access
token's signature *and* re-checks that the session behind it is still live, so logging
out ends access immediately rather than leaving an unexpired access token working until
it lapses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import load_active_session
from app.auth.tokens import InvalidAccessTokenError, decode_access_token
from app.db.session import get_session
from app.models.user import UserAccount

# auto_error=False so a missing header produces our own 401 with a consistent body
# rather than FastAPI's 403.
_bearer = HTTPBearer(auto_error=False)

UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def jwt_secret(request: Request) -> str:
    """The signing key resolved at startup (see `app.main`)."""
    secret = getattr(request.app.state, "jwt_secret", None)
    if not isinstance(secret, str):  # pragma: no cover - unreachable once started
        raise RuntimeError("jwt secret was not resolved at startup")
    return secret


@dataclass(frozen=True)
class Authenticated:
    """The signed-in account and the session the token came from.

    Routes that only need identity depend on `current_user`; logout needs to know
    which session to end, which is why the session id is carried here rather than
    decoded a second time in the handler.
    """

    account: UserAccount
    session_id: uuid.UUID


async def authenticated(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    secret: Annotated[str, Depends(jwt_secret)],
) -> Authenticated:
    """The signed-in account, or a 401.

    Every failure mode returns the same body. Distinguishing "no such session" from
    "expired" from "revoked" would tell a caller holding a stolen token which it is.
    """
    if credentials is None:
        raise UNAUTHENTICATED

    try:
        claims = decode_access_token(credentials.credentials, secret=secret)
    except InvalidAccessTokenError as exc:
        raise UNAUTHENTICATED from exc

    now = datetime.now(UTC)
    if await load_active_session(session, session_id=claims.session_id, now=now) is None:
        # The token is validly signed but its session was revoked or expired. This is
        # the check that makes logout take effect immediately.
        raise UNAUTHENTICATED

    account = (
        await session.execute(select(UserAccount).where(UserAccount.id == claims.user_id))
    ).scalar_one_or_none()
    if account is None or not account.active:
        raise UNAUTHENTICATED
    return Authenticated(account=account, session_id=claims.session_id)


async def current_user(
    auth: Annotated[Authenticated, Depends(authenticated)],
) -> UserAccount:
    """Identity only, for the routes that do not care which session it is."""
    return auth.account


AuthenticatedSession = Annotated[Authenticated, Depends(authenticated)]
CurrentUser = Annotated[UserAccount, Depends(current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
JwtSecret = Annotated[str, Depends(jwt_secret)]
