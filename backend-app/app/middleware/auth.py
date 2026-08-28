import json
import logging
import time
from typing import Any

import httpx
from jose import jwt, JWTError

from app.config import settings

logger = logging.getLogger(__name__)

_jwks_cache: dict[str, Any] = {}
_jwks_cache_time: float = 0
_JWKS_CACHE_TTL = 3600  # 1 hour


async def _get_jwks() -> dict[str, Any]:
    global _jwks_cache, _jwks_cache_time
    if _jwks_cache and (time.time() - _jwks_cache_time) < _JWKS_CACHE_TTL:
        return _jwks_cache

    url = (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com"
        f"/{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=5)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_time = time.time()
        return _jwks_cache


async def verify_token(token: str) -> dict[str, Any]:
    """Verify a Cognito JWT and return its claims."""
    jwks = await _get_jwks()
    issuer = (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com"
        f"/{settings.cognito_user_pool_id}"
    )

    # Get the kid from the token header
    headers = jwt.get_unverified_headers(token)
    kid = headers.get("kid")

    # Find the matching key
    key = None
    for k in jwks.get("keys", []):
        if k["kid"] == kid:
            key = k
            break

    if not key:
        raise JWTError("Token key ID not found in JWKS")

    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        issuer=issuer,
        options={"verify_aud": False},  # Cognito ID tokens use 'aud', access tokens don't
    )
    return claims
