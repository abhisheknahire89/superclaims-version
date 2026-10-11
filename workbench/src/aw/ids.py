"""Sortable identifiers: PREFIX-<UUIDv7 hex>. Time-ordered, so B-tree inserts stay local."""
from __future__ import annotations

import os
import time
import hashlib
import json


def uuid7_hex() -> str:
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76                      # version 7
    value |= (rand >> 68 & 0xFFF) << 64     # rand_a (12 bits)
    value |= 0b10 << 62                     # variant
    value |= rand & ((1 << 62) - 1)         # rand_b
    return f"{value:032x}"


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid7_hex()}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()
