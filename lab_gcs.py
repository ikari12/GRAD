"""Resolve large workstation assets from a private lab GCS bucket.

Local files win when present. Otherwise ``lab_assets.json`` (repo root) maps
repo-relative paths to ``gs://`` URIs. JSON/CSV should be streamed; weights
may be downloaded to ``~/.cache/lab-gcs`` (outside the repo).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import IO, Any, Optional
from urllib.parse import urlparse

_ASSETS_NAME = "lab_assets.json"


def find_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    chain = (p, *p.parents)
    for cand in chain:
        if (cand / _ASSETS_NAME).is_file():
            return cand
    for cand in chain:
        if (cand / ".git").exists():
            return cand
    return p


def _load_map(root: Path) -> dict[str, str]:
    path = root / _ASSETS_NAME
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(k).replace("\\", "/"): str(v).strip() for k, v in data.items()}


def gcs_uri_for(path: str | Path, *, root: Path | None = None) -> Optional[str]:
    p = Path(path).expanduser()
    sidecar = Path(str(p) + ".gcsuri")
    if sidecar.is_file():
        uri = sidecar.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        if uri.startswith("gs://"):
            return uri
    p = p.resolve()
    root = (root or find_root(p)).resolve()
    mapping = _load_map(root)
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        rel = Path(path).as_posix().lstrip("./")
    if rel in mapping:
        return mapping[rel]
    if p.name in mapping:
        return mapping[p.name]
    return mapping.get(Path(path).as_posix().lstrip("./"))


def exists(path: str | Path) -> bool:
    p = Path(path)
    if p.is_file() and p.stat().st_size > 0:
        return True
    return gcs_uri_for(p) is not None


def _blob(uri: str):
    from google.cloud import storage

    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path:
        raise ValueError(f"not a gs:// URI: {uri}")
    client = storage.Client()
    return client.bucket(parsed.netloc).blob(parsed.path.lstrip("/"))


def open_text(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    errors: str = "ignore",
) -> IO[str]:
    p = Path(path)
    if p.is_file() and p.stat().st_size > 0:
        return p.open("r", encoding=encoding, errors=errors)
    uri = gcs_uri_for(p)
    if not uri:
        raise FileNotFoundError(
            f"{p} is missing locally and has no lab_assets.json / .gcsuri mapping"
        )
    return _blob(uri).open("rt", encoding=encoding, errors=errors)


def cache_dir() -> Path:
    return Path(os.environ.get("LAB_GCS_CACHE", str(Path.home() / ".cache" / "lab-gcs")))


def ensure_file(path: str | Path, *, dest: Path | None = None) -> Path:
    """Return a local path to the bytes. Does not write into the repo unless dest says so."""
    p = Path(path)
    if p.is_file() and p.stat().st_size > 0:
        return p
    uri = gcs_uri_for(p)
    if not uri:
        raise FileNotFoundError(
            f"{p} is missing locally and has no lab_assets.json / .gcsuri mapping"
        )
    parsed = urlparse(uri)
    out = dest or (cache_dir() / parsed.netloc / parsed.path.lstrip("/"))
    if out.is_file() and out.stat().st_size > 0:
        blob = _blob(uri)
        blob.reload()
        if blob.size and out.stat().st_size == blob.size:
            return out
    out.parent.mkdir(parents=True, exist_ok=True)
    _blob(uri).download_to_filename(str(out), timeout=None)
    return out


def torch_load(path: str | Path, **kwargs: Any) -> Any:
    """Load a .pt/.pth from disk or GCS without leaving a copy in the repo."""
    import io

    import torch

    p = Path(path)
    if p.is_file() and p.stat().st_size > 0:
        return torch.load(str(p), **kwargs)
    uri = gcs_uri_for(p)
    if not uri:
        raise FileNotFoundError(
            f"{p} is missing locally and has no lab_assets.json / .gcsuri mapping"
        )
    data = _blob(uri).download_as_bytes(timeout=None)
    return torch.load(io.BytesIO(data), **kwargs)
