"""Application context: settings, database handles, object store and extraction provider wired once."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .db import Database
from .extraction.providers import BedrockClaudeProvider, ExtractionProvider, FixtureProvider, HeuristicProvider
from .settings import Settings
from .storage import LocalWormStore, ObjectStore


@dataclass
class AppContext:
    settings: Settings
    db: Database
    worker_db: Database | None
    store: ObjectStore
    provider: ExtractionProvider

    @property
    def schema_dir(self) -> Path:
        return self.settings.pack_dir / "schemas"


def build(settings: Settings) -> AppContext:
    db = Database(settings.database_url)
    worker_db = Database(settings.worker_dsn) if settings.worker_dsn else None
    store = LocalWormStore(settings.object_store_dir)
    if settings.extraction_provider == "fixture":
        provider: ExtractionProvider = FixtureProvider(settings.fixture_dir or Path("."))
    elif settings.extraction_provider not in ("heuristic", "layout"):
        raise RuntimeError("Hosted/model extraction is disabled in this local product; use layout, heuristic or fixture")
    else:
        provider = HeuristicProvider()
    return AppContext(settings, db, worker_db, store, provider)
