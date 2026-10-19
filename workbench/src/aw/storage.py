"""Object storage for original documents and derived artefacts.

`LocalWormStore` is the development stand-in for S3 with Object Lock (ADR-07): keys are
tenant/claim/document/sha256, objects are written once and never overwritten, and reads verify
the stored hash. `S3ObjectLockStore` is the production adapter; it needs boto3 and AWS credentials
and is not exercised in the Phase 1 build environment.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    def put_once(self, key: str, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...


class ImmutableObjectError(Exception):
    pass


class LocalWormStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if ".." in key.split("/") or key.startswith("/"):
            raise ValueError("invalid object key")
        return self.root / key

    def put_once(self, key: str, data: bytes) -> str:
        p = self._path(key)
        digest = hashlib.sha256(data).hexdigest()
        if p.exists():
            if hashlib.sha256(p.read_bytes()).hexdigest() == digest:
                self._checksum(p,digest)
                return digest            # recover publication interrupted before checksum
            raise ImmutableObjectError(f"object {key} already exists with different content")
        p.parent.mkdir(parents=True, exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.aw-write-',dir=p.parent)
        tmp=Path(name)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,0o444)
            try:os.link(tmp,p)
            except FileExistsError:
                if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ImmutableObjectError('object already exists with different content')
            self._checksum(p,digest)
        finally:tmp.unlink(missing_ok=True)
        return digest

    def _checksum(self,p:Path,digest:str):
        side=p.parent/(p.name+'.sha256')
        fd,name=tempfile.mkstemp(prefix='.aw-write-',dir=p.parent);tmp=Path(name)
        try:
            with os.fdopen(fd,'w') as stream:stream.write(digest);stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,0o444)
            try:os.link(tmp,side)
            except FileExistsError:
                if side.read_text().strip()!=digest:raise ImmutableObjectError('existing checksum differs from object')
        finally:tmp.unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        p = self._path(key)
        data = p.read_bytes()
        side = p.parent / (p.name + ".sha256")
        if not side.exists() or hashlib.sha256(data).hexdigest() != side.read_text().strip():
            raise ImmutableObjectError(f"object {key} failed its integrity check")
        return data

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3ObjectLockStore:  # pragma: no cover - requires boto3 + AWS; not run in the Phase 1 build environment
    """Production adapter: S3 bucket with Object Lock in compliance mode (retention set per tenant)."""

    def __init__(self, bucket: str, retention_days: int, kms_key_id: str | None = None):
        import boto3  # type: ignore
        self.s3 = boto3.client("s3")
        self.bucket, self.retention_days, self.kms_key_id = bucket, retention_days, kms_key_id

    def put_once(self, key: str, data: bytes) -> str:
        import base64
        from datetime import datetime, timedelta, timezone
        digest = hashlib.sha256(data).hexdigest()
        if self.exists(key):
            return digest
        kwargs = dict(Bucket=self.bucket, Key=key, Body=data, ChecksumSHA256=base64.b64encode(bytes.fromhex(digest)).decode(),
                      ObjectLockMode="COMPLIANCE",
                      ObjectLockRetainUntilDate=datetime.now(timezone.utc) + timedelta(days=self.retention_days))
        if self.kms_key_id:
            kwargs.update(ServerSideEncryption="aws:kms", SSEKMSKeyId=self.kms_key_id)
        self.s3.put_object(**kwargs)
        return digest

    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False
