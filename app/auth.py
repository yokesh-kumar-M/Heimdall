"""Auth — resolving every inbound request to a tenant.

Three paths, all converge on `TenantContext`:

  1. **Clerk session JWT** (dashboard / admin REST). The Authorization header
     is `Bearer <Clerk JWT>`. We verify the JWT against Clerk's JWKS and use
     the `org_id` claim if present (the user is operating in an org), else
     `sub` (the user themselves). Either way you get a string tenant ID.

  2. **Heimdall API key** (proxy / SDK). The Authorization header is
     `Bearer sk_hd_...`. We SHA-256 the key, look it up in `api_keys`, and
     resolve the owning tenant.

  3. **Default tenant** (single-user dev, `MULTI_TENANT_MODE=false`). No auth
     required; everything is attributed to the configured default tenant.

Routes use `Depends(get_tenant_ctx)` or — for routes that ONLY accept Clerk
sessions, never API keys — `Depends(get_dashboard_ctx)`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.auth import ApiKeyRepo, TenantRepo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    auth_method: str  # "clerk_jwt" | "api_key" | "default" | "admin_token"
    user_id: str | None = None
    org_id: str | None = None
    api_key_id: int | None = None
    email: str | None = None


# ---------------------------------------------------------------------------
# Clerk JWT verification
# ---------------------------------------------------------------------------
class ClerkVerifier:
    """Verifies Clerk session JWTs against the JWKS endpoint.

    The JWKS is cached for an hour by PyJWKClient. Rotation just works on
    its own next refresh.
    """

    def __init__(self, jwks_url: str, issuer: str) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._jwks_client: PyJWKClient | None = (
            PyJWKClient(jwks_url, cache_keys=True, lifespan=3600) if jwks_url else None
        )

    @property
    def configured(self) -> bool:
        return self._jwks_client is not None

    def verify(self, token: str) -> dict[str, Any]:
        if not self._jwks_client:
            raise HTTPException(status_code=503, detail="Clerk not configured")
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256", "ES256"],
                issuer=self._issuer or None,
                options={
                    # `aud` is optional on Clerk session tokens — they bind to
                    # the issuer instead. We verify exp + iat + iss.
                    "verify_aud": False,
                    "require": ["exp", "iat"],
                },
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Session token expired") from None
        except jwt.InvalidIssuerError:
            raise HTTPException(status_code=401, detail="Invalid token issuer") from None
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

        return claims


_verifier_singleton: ClerkVerifier | None = None


def get_verifier(settings: Settings = Depends(get_settings)) -> ClerkVerifier:
    global _verifier_singleton
    if _verifier_singleton is None:
        _verifier_singleton = ClerkVerifier(
            jwks_url=settings.clerk_jwks_url, issuer=settings.clerk_issuer
        )
    return _verifier_singleton


# ---------------------------------------------------------------------------
# Header extraction
# ---------------------------------------------------------------------------
def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


# ---------------------------------------------------------------------------
# Main dependencies
# ---------------------------------------------------------------------------
async def get_tenant_ctx(
    request: Request,
    settings: Settings = Depends(get_settings),
    verifier: ClerkVerifier = Depends(get_verifier),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    """Resolve the request to a tenant via any supported auth method.

    Used by the proxy routes (which accept both API keys and Clerk JWTs) and
    by API routes the dashboard hits.
    """
    bearer = _extract_bearer(request)

    # 1. Admin token (operator escape hatch)
    if bearer and settings.admin_api_token and bearer == settings.admin_api_token:
        return TenantContext(
            tenant_id=request.headers.get("x-tenant-id") or settings.default_tenant_id,
            auth_method="admin_token",
        )

    # 2. Heimdall API key (sk_hd_)
    if bearer and bearer.startswith("sk_hd_"):
        repo = ApiKeyRepo(session)
        row = await repo.lookup_by_plain(bearer)
        if row is None:
            raise HTTPException(status_code=401, detail="Invalid Heimdall API key")
        return TenantContext(
            tenant_id=row.tenant_id,
            auth_method="api_key",
            api_key_id=row.id,
        )

    # 3. Clerk JWT (typically the dashboard's fetch wrapper sends this)
    if bearer and verifier.configured:
        try:
            claims = verifier.verify(bearer)
        except HTTPException:
            if settings.multi_tenant_mode:
                raise
            # fall through to default tenant in single-user mode
        else:
            tenant_id = claims.get("org_id") or claims.get("sub")
            if not tenant_id:
                raise HTTPException(status_code=401, detail="Token missing sub/org_id")
            # ensure tenant row exists
            await TenantRepo(session).ensure(
                tenant_id, display_name=claims.get("email") or None
            )
            return TenantContext(
                tenant_id=str(tenant_id),
                auth_method="clerk_jwt",
                user_id=claims.get("sub"),
                org_id=claims.get("org_id"),
                email=claims.get("email"),
            )

    # 4. Default tenant (single-user mode only)
    if not settings.multi_tenant_mode:
        await TenantRepo(session).ensure(settings.default_tenant_id, display_name="Default")
        return TenantContext(
            tenant_id=settings.default_tenant_id,
            auth_method="default",
        )

    raise HTTPException(
        status_code=401,
        detail="Authentication required (Clerk JWT or Heimdall API key).",
    )


async def get_dashboard_ctx(
    request: Request,
    settings: Settings = Depends(get_settings),
    verifier: ClerkVerifier = Depends(get_verifier),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    """Same as `get_tenant_ctx` but rejects API keys.

    Used for management endpoints (creating/revoking API keys, setting
    budgets) so a leaked API key can't escalate to managing the account.
    """
    ctx = await get_tenant_ctx(request, settings, verifier, session)
    if ctx.auth_method == "api_key":
        raise HTTPException(
            status_code=403,
            detail="This endpoint requires a dashboard session (Clerk JWT), not an API key.",
        )
    return ctx
