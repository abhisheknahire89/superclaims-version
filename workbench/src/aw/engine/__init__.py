"""Deterministic rule engine. Models never compute money; this module does."""
from .core import ENGINE_VERSION, RULE_VERSIONS, ConfigurationError, evaluate, line_fingerprint  # noqa: F401
