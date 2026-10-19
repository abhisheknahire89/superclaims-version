"""Application errors. Any `AppError` raised inside a request becomes an RFC 9457 problem response with its status,
code and `extra` members (aw.api.core). Domain modules subclass it so the API maps them without a lookup table."""
from __future__ import annotations


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.extra = status, code, extra or {}
