"""Pluggable object storage adapter.

Backends supported (selected via STORAGE_BACKEND env var):
  - "local"     : local filesystem (default, works on Render Disks or any host)
  - "s3"        : AWS S3 or any S3-compatible service (Cloudflare R2, Backblaze
                  B2, MinIO, DigitalOcean Spaces) via boto3
  - "emergent"  : Emergent-managed object storage (legacy, only works inside
                  Emergent runtime — kept for backward compatibility)

Public API is identical across all backends so the rest of the codebase
(routes_ops.py, routes_reports.py, server.py) does not change:

    init_storage(force: bool = False) -> str | None
    put_object(path: str, data: bytes, content_type: str) -> dict
    get_object(path: str) -> tuple[bytes, str]

Environment variables (all optional except S3 credentials when S3 chosen):

  STORAGE_BACKEND        local | s3 | emergent   (default: local)
  STORAGE_DIR            local FS root           (default: /var/data/receipts,
                                                  falls back to ./data/receipts)

  # S3 backend
  S3_BUCKET              bucket name (required for s3)
  S3_REGION              e.g. ap-southeast-2   (default: us-east-1)
  S3_ENDPOINT_URL        custom endpoint for R2/MinIO/etc. (optional)
  AWS_ACCESS_KEY_ID      standard AWS credentials
  AWS_SECRET_ACCESS_KEY  standard AWS credentials

  # Emergent backend (legacy)
  INTEGRATION_PROXY_URL  proxy base URL
  EMERGENT_LLM_KEY       key to obtain a storage_key
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

APP_NAME = "urbandotted-expense-book"

MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "pdf": "application/pdf", "csv": "text/csv",
    "txt": "text/plain",
}
ALLOWED_EXT = set(MIME_TYPES.keys())
MAX_SIZE = 10 * 1024 * 1024  # 10 MB


# --------------------------------------------------------------------------- #
# Backend implementations
# --------------------------------------------------------------------------- #
class _LocalStorage:
    """Filesystem-based storage. Ideal for Render Disks or any persistent volume."""

    def __init__(self) -> None:
        default_dir = "/var/data/receipts"
        chosen = os.environ.get("STORAGE_DIR", "").strip() or default_dir
        # Fall back to ./data/receipts if the preferred dir is not writable
        try:
            Path(chosen).mkdir(parents=True, exist_ok=True)
            self.root = Path(chosen)
        except (PermissionError, OSError):
            fallback = Path(os.getcwd()) / "data" / "receipts"
            fallback.mkdir(parents=True, exist_ok=True)
            self.root = fallback
        logger.info("Local storage root: %s", self.root)

    def init(self, force: bool = False) -> str:  # noqa: ARG002 - signature parity
        self.root.mkdir(parents=True, exist_ok=True)
        return str(self.root)

    def _resolve(self, path: str) -> Path:
        # Avoid path traversal
        p = (self.root / path).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("Invalid storage path")
        return p

    def put(self, path: str, data: bytes, content_type: str) -> dict:  # noqa: ARG002
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return {"path": path, "size": len(data)}

    def get(self, path: str) -> Tuple[bytes, str]:
        p = self._resolve(path)
        if not p.exists():
            raise FileNotFoundError(path)
        ext = p.suffix.lstrip(".").lower()
        content_type = MIME_TYPES.get(ext, "application/octet-stream")
        return p.read_bytes(), content_type


class _S3Storage:
    """S3-compatible storage (AWS S3, Cloudflare R2, MinIO, B2, DO Spaces)."""

    def __init__(self) -> None:
        import boto3  # imported lazily so local users don't need boto3 configured
        self.bucket = os.environ.get("S3_BUCKET", "").strip()
        if not self.bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 requires S3_BUCKET env var")
        region = os.environ.get("S3_REGION", "us-east-1").strip() or "us-east-1"
        endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip() or None
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )

    def init(self, force: bool = False) -> str:  # noqa: ARG002
        # Head bucket to validate credentials + existence
        self.client.head_bucket(Bucket=self.bucket)
        return self.bucket

    def put(self, path: str, data: bytes, content_type: str) -> dict:
        self.client.put_object(Bucket=self.bucket, Key=path, Body=data,
                               ContentType=content_type)
        return {"path": path, "size": len(data)}

    def get(self, path: str) -> Tuple[bytes, str]:
        obj = self.client.get_object(Bucket=self.bucket, Key=path)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")


class _EmergentStorage:
    """Legacy Emergent-managed object storage. Kept for backward compatibility."""

    def __init__(self) -> None:
        import requests  # noqa: F401 - imported lazily
        base = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() \
            or "https://integrations.emergentagent.com"
        self.storage_url = base.rstrip("/") + "/objstore/api/v1/storage"
        self.key_env = os.environ.get("EMERGENT_LLM_KEY")
        self.storage_key: Optional[str] = None

    def _init_key(self, force: bool = False) -> str:
        import requests
        if self.storage_key and not force:
            return self.storage_key
        resp = requests.post(f"{self.storage_url}/init",
                             json={"emergent_key": self.key_env}, timeout=30)
        resp.raise_for_status()
        self.storage_key = resp.json()["storage_key"]
        return self.storage_key

    def init(self, force: bool = False) -> str:
        return self._init_key(force=force)

    def put(self, path: str, data: bytes, content_type: str) -> dict:
        import requests
        key = self._init_key()
        resp = requests.put(f"{self.storage_url}/objects/{path}",
                            headers={"X-Storage-Key": key, "Content-Type": content_type},
                            data=data, timeout=120)
        if resp.status_code == 404:
            key = self._init_key(force=True)
            resp = requests.put(f"{self.storage_url}/objects/{path}",
                                headers={"X-Storage-Key": key, "Content-Type": content_type},
                                data=data, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str) -> Tuple[bytes, str]:
        import requests
        key = self._init_key()
        resp = requests.get(f"{self.storage_url}/objects/{path}",
                            headers={"X-Storage-Key": key}, timeout=60)
        if resp.status_code == 404:
            key = self._init_key(force=True)
            resp = requests.get(f"{self.storage_url}/objects/{path}",
                                headers={"X-Storage-Key": key}, timeout=60)
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# --------------------------------------------------------------------------- #
# Factory / public API
# --------------------------------------------------------------------------- #
_BACKEND_INSTANCE = None


def _get_backend():
    global _BACKEND_INSTANCE
    if _BACKEND_INSTANCE is not None:
        return _BACKEND_INSTANCE
    choice = (os.environ.get("STORAGE_BACKEND") or "local").strip().lower()
    if choice == "s3":
        _BACKEND_INSTANCE = _S3Storage()
    elif choice == "emergent":
        _BACKEND_INSTANCE = _EmergentStorage()
    else:
        _BACKEND_INSTANCE = _LocalStorage()
    logger.info("Storage backend: %s", choice)
    return _BACKEND_INSTANCE


def init_storage(force: bool = False):
    """Initialise the configured storage backend (idempotent)."""
    return _get_backend().init(force=force)


def put_object(path: str, data: bytes, content_type: str) -> dict:
    return _get_backend().put(path, data, content_type)


def get_object(path: str):
    return _get_backend().get(path)
