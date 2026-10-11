"""Authentication and authorisation.

Phase 1 ships a development token scheme: `Authorization: Bearer <payload>.<signature>` where the payload
is base64url JSON {sub, tenant, exp} and the signature is HMAC-SHA256 with AW_DEV_TOKEN_SECRET. Roles and
approval limits are NOT taken from the token: they are read from role_assignment in the database on every
request, so revoking a role takes effect immediately. Production uses OIDC (ADR-10); the verifier is the only
part that changes.

The permission map mirrors 03-workflows-and-UX.md §4.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field

from .db import Conn

ROLES = ("PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR", "AUDITOR", "FWA_ANALYST", "CONFIG_ADMIN", "TENANT_ADMIN", "READ_ONLY")

# action -> roles allowed (03 §4). Limits and second approval are enforced in aw.decisions.
PERMISSIONS: dict[str, set[str]] = {
    "claim.view": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR", "AUDITOR", "FWA_ANALYST", "READ_ONLY"},
    "claim.create": {"PROCESSOR", "SUPERVISOR"},
    "claim.assign": {"SUPERVISOR"},
    "claim.withdraw": {"SUPERVISOR"},
    "claim.reopen": {"SUPERVISOR"},
    "document.upload": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR"},
    "fact.correct": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR"},
    "line.reclassify": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR"},
    "adjustment.override": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR"},
    "finding.resolve_clinical": {"MEDICAL_OFFICER", "SUPERVISOR"},
    "finding.resolve": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR"},
    "finding.dismiss_high_anomaly": {"SUPERVISOR", "FWA_ANALYST"},
    "claim.hold": {"SUPERVISOR", "FWA_ANALYST"},
    "query.draft": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR"},
    "query.approve": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR"},
    "decision.approve": {"PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR"},
    "decision.repudiate": {"SUPERVISOR"},
    "decision.close_duplicate": {"SUPERVISOR"},
    "decision.second_approve": {"SUPERVISOR"},
    "audit.export": {"AUDITOR", "SUPERVISOR"},
    "config.author": {"CONFIG_ADMIN"},
    "config.publish": {"CONFIG_ADMIN", "TENANT_ADMIN"},
    "admin.users": {"TENANT_ADMIN"},
}


class AuthError(Exception):
    status = 401


class Forbidden(Exception):
    status = 403


@dataclass
class Principal:
    user_id: str
    tenant_id: str
    roles: set[str] = field(default_factory=set)
    approval_limit_paise: int | None = None

    def can(self, action: str) -> bool:
        return bool(self.roles & PERMISSIONS[action])

    def require(self, action: str):
        if not self.can(action):
            raise Forbidden(f"{self.user_id} lacks permission {action}")

    @property
    def actor(self) -> str:
        return f"USER:{self.user_id}"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_dev_token(secret: str, user_id: str, tenant_id: str, ttl_seconds: int = 8 * 3600) -> str:
    payload = _b64(json.dumps({"sub": user_id, "tenant": tenant_id, "exp": int(time.time()) + ttl_seconds}).encode())
    sig = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_dev_token(secret: str, token: str) -> tuple[str, str]:
    try:
        payload, sig = token.split(".")
    except ValueError as e:
        raise AuthError("malformed token") from e
    expect = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expect, sig):
        raise AuthError("bad token signature")
    data = json.loads(_unb64(payload))
    if data.get("exp", 0) < time.time():
        raise AuthError("token expired")
    return data["sub"], data["tenant"]


def load_principal(conn: Conn, tenant_id: str, user_id: str) -> Principal:
    user = conn.fetch_one("SELECT user_id, is_active FROM app_user WHERE tenant_id = $1 AND user_id = $2", tenant_id, user_id)
    if not user or not user["is_active"]:
        raise AuthError("unknown or inactive user")
    rows = conn.fetch_all(
        "SELECT role, approval_limit_paise FROM role_assignment WHERE tenant_id = $1 AND user_id = $2"
        " AND valid_from <= now() AND (valid_to IS NULL OR valid_to > now())", tenant_id, user_id)
    limits = [r["approval_limit_paise"] for r in rows if r["approval_limit_paise"] is not None]
    return Principal(user_id, tenant_id, {r["role"] for r in rows}, max(limits) if limits else None)
