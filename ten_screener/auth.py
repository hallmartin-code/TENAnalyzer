"""Shared-password access control for hosted deployments.

A public URL without a password would let anyone run analyses on your Anthropic
API key. On Railway the app refuses to run until APP_PASSWORD is set; locally the
password is optional.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Mapping

_HOSTED_MARKERS = ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID", "TEN_REQUIRE_PASSWORD")


def is_hosted(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return any(env.get(key) for key in _HOSTED_MARKERS)


def configured_password(env: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    value = (env.get("APP_PASSWORD") or "").strip()
    return value or None


def password_matches(given: str, expected: str) -> bool:
    """Constant-time comparison, so response timing reveals nothing about the password."""
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))
