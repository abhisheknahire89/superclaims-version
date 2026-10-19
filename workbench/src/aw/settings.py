"""Configuration from environment variables (12-factor). No secret has a default outside the test environment.

`workbench/.env` (created by scripts/make_env.py, git-ignored) is read when present; real environment variables win.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("aw.settings")
_HERE = Path(__file__).resolve()
WORKBENCH_DIR = _HERE.parents[2]
TEST_SECRET = "test-only-secret-not-for-use"


@dataclass(frozen=True)
class Settings:
    database_url: str
    worker_dsn: str | None
    object_store_dir: Path
    auth_mode: str              # "local" (passwords + sessions) or "oidc" (interface only, ADR-15)
    secret_key: str             # signs session tokens and short-lived page/upload URLs
    extraction_provider: str    # "layout" (default) | "heuristic" | "fixture" | "ollama" | "bedrock"
    fixture_dir: Path | None
    pack_dir: Path              # research pack root (schemas, config, api)
    environment: str            # "dev" | "test" | "prod"
    ocr_engine: str             # "tesseract" | "none"
    ollama_url: str | None
    ollama_model: str | None

    @property
    def dev_token_secret(self) -> str:   # kept for callers written against the Phase 1 name
        return self.secret_key


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def load() -> Settings:
    file_values = _read_env_file(Path(os.environ.get("AW_ENV_FILE", str(WORKBENCH_DIR / ".env"))))
    get = lambda k, d=None: os.environ.get(k, file_values.get(k, d))  # noqa: E731
    env = get("AW_ENV", "dev")
    secret = get("AW_SECRET_KEY") or get("AW_DEV_TOKEN_SECRET")
    if not secret:
        if env == "prod":
            raise RuntimeError("AW_SECRET_KEY must be set when AW_ENV=prod")
        if env == "test":
            secret = TEST_SECRET
        else:
            secret = secrets.token_urlsafe(48)
            log.warning("AW_SECRET_KEY is not set; using an ephemeral key (sessions end when the server restarts). Run `make env`.")
    auth_mode = get("AW_AUTH_MODE", "local")
    if auth_mode not in ("local", "oidc"):
        raise RuntimeError(f"unknown AW_AUTH_MODE {auth_mode}")
    return Settings(
        database_url=get("AW_DATABASE_URL", ""),
        worker_dsn=get("AW_WORKER_DSN"),
        object_store_dir=Path(get("AW_OBJECT_STORE_DIR", str(WORKBENCH_DIR / ".objects"))),
        auth_mode=auth_mode,
        secret_key=secret,
        extraction_provider=get("AW_EXTRACTION_PROVIDER", "layout"),
        fixture_dir=Path(get("AW_FIXTURE_DIR")) if get("AW_FIXTURE_DIR") else None,
        pack_dir=Path(get("AW_PACK_DIR", str(WORKBENCH_DIR.parent))),
        environment=env,
        ocr_engine=get("AW_OCR_ENGINE", "tesseract"),
        ollama_url=get("AW_OLLAMA_URL"),
        ollama_model=get("AW_OLLAMA_MODEL"),
    )
