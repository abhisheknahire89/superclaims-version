"""Configuration from environment variables (12-factor). No secrets have defaults outside dev mode."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    worker_dsn: str | None
    object_store_dir: Path
    auth_mode: str              # "dev-token" (HMAC-signed bearer tokens) or "oidc" (not implemented in Phase 1)
    dev_token_secret: str | None
    extraction_provider: str    # "heuristic" | "fixture" | "bedrock"
    fixture_dir: Path | None
    pack_dir: Path              # research pack root (schemas, config, api)
    environment: str            # "dev" | "test" | "prod"


def load() -> Settings:
    here = Path(__file__).resolve()
    default_pack = here.parents[3]  # workbench/src/aw/settings.py -> pack root is workbench/..
    env = os.environ.get("AW_ENV", "dev")
    secret = os.environ.get("AW_DEV_TOKEN_SECRET")
    if env == "prod" and os.environ.get("AW_AUTH_MODE", "dev-token") == "dev-token":
        raise RuntimeError("dev-token authentication is not allowed when AW_ENV=prod")
    if secret is None and env in ("dev", "test"):
        secret = "dev-only-secret-change-me"
    return Settings(
        database_url=os.environ.get("AW_DATABASE_URL", ""),
        worker_dsn=os.environ.get("AW_WORKER_DSN"),
        object_store_dir=Path(os.environ.get("AW_OBJECT_STORE_DIR", str(here.parents[2] / ".objects"))),
        auth_mode=os.environ.get("AW_AUTH_MODE", "dev-token"),
        dev_token_secret=secret,
        extraction_provider=os.environ.get("AW_EXTRACTION_PROVIDER", "heuristic"),
        fixture_dir=Path(os.environ["AW_FIXTURE_DIR"]) if os.environ.get("AW_FIXTURE_DIR") else None,
        pack_dir=Path(os.environ.get("AW_PACK_DIR", str(default_pack))),
        environment=env,
    )
