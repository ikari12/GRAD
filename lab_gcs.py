"""Resolve large workstation assets from a private lab GCS bucket.

Local files win when present. Otherwise ``lab_assets.json`` (repo root) maps
repo-relative paths to ``gs://`` URIs. JSON/CSV should be streamed; weights
may be downloaded to ``~/.cache/lab-gcs`` (outside the repo).

On a Cursor Cloud Agent VM, GCS uses Workload Identity Federation: mint a
short-lived OIDC JWT from ``CURSOR_AGENT_SOCKET``, exchange it at STS, and
impersonate ``cursor-lab-reader`` (lab buckets only). Laptops keep using ADC.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any, Optional
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

_ASSETS_NAME = "lab_assets.json"

_GCP_PROJECT = "gpx-analytics-service"
_GCP_PROJECT_NUMBER = "1066463940672"
_WIF_POOL = "cursor-cloud"
_WIF_PROVIDER = "cursor"
_LAB_SA = f"cursor-lab-reader@{_GCP_PROJECT}.iam.gserviceaccount.com"
_JWT_AUD = (
    f"https://iam.googleapis.com/projects/{_GCP_PROJECT_NUMBER}/locations/global/"
    f"workloadIdentityPools/{_WIF_POOL}/providers/{_WIF_PROVIDER}"
)
_STS_AUDIENCE = (
    f"//iam.googleapis.com/projects/{_GCP_PROJECT_NUMBER}/locations/global/"
    f"workloadIdentityPools/{_WIF_POOL}/providers/{_WIF_PROVIDER}"
)
_DEFAULT_AGENT_SOCKET = "/run/cursor/api.sock"


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


def agent_socket_path() -> Path:
    return Path(os.environ.get("CURSOR_AGENT_SOCKET", _DEFAULT_AGENT_SOCKET))


def on_cloud_agent() -> bool:
    sock = agent_socket_path()
    try:
        return sock.is_socket()
    except OSError:
        return False


def _unix_http_json(method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    sock_path = str(agent_socket_path())
    body = json.dumps(payload).encode("utf-8")
    req = (
        f"{method} {path} HTTP/1.1\r\n"
        f"Host: cursor-agent\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("ascii") + body
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(15)
    try:
        conn.connect(sock_path)
        conn.sendall(req)
        chunks: list[bytes] = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        conn.close()
    raw = b"".join(chunks)
    header, sep, rest = raw.partition(b"\r\n\r\n")
    if not sep:
        raise RuntimeError("Cursor OIDC socket returned an empty HTTP response")
    status_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
    parts = status_line.split(" ", 2)
    code = int(parts[1]) if len(parts) > 1 else 0
    if code != 200:
        raise RuntimeError(f"Cursor OIDC mint failed ({status_line}): {rest[:500]!r}")
    return json.loads(rest.decode("utf-8"))


def mint_cursor_oidc(audience: str = _JWT_AUD) -> tuple[str, int]:
    """Return (jwt, expires_at_unix). Tokens last 5 minutes; cache until expiry."""
    data = _unix_http_json("POST", "/v1/tokens/oidc", {"aud": audience})
    token = data.get("token")
    exp = data.get("expires_at")
    if not token or not exp:
        raise RuntimeError(f"Cursor OIDC mint missing token/expires_at: {data!r}")
    return str(token), int(exp)


def _http_json(url: str, *, data: bytes, headers: dict[str, str]) -> dict[str, Any]:
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — surface STS/IAM errors to the caller
        raise RuntimeError(f"GCP token exchange failed for {url}: {exc}") from exc


def _parse_expiry(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def exchange_cursor_oidc() -> tuple[str, datetime]:
    """OIDC JWT → STS federated token → lab SA access token."""
    id_token, _ = mint_cursor_oidc(_JWT_AUD)
    sts = _http_json(
        "https://sts.googleapis.com/v1/token",
        data=urlencode(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "audience": _STS_AUDIENCE,
                "scope": "https://www.googleapis.com/auth/cloud-platform",
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "subject_token": id_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    federated = sts.get("access_token")
    if not federated:
        raise RuntimeError(f"STS response missing access_token: {sts!r}")
    sa = _http_json(
        "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
        f"{_LAB_SA}:generateAccessToken",
        data=json.dumps(
            {
                "scope": ["https://www.googleapis.com/auth/devstorage.read_write"],
                "lifetime": "3600s",
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {federated}",
            "Content-Type": "application/json",
        },
    )
    token = sa.get("accessToken")
    expire_time = sa.get("expireTime")
    if not token or not expire_time:
        raise RuntimeError(f"iamcredentials response missing token: {sa!r}")
    return str(token), _parse_expiry(str(expire_time))


_wif_creds: Any = None


def _wif_credentials():
    global _wif_creds
    if _wif_creds is not None:
        return _wif_creds
    from google.auth.credentials import Credentials as GoogleCredentials

    class _LabWifCredentials(GoogleCredentials):
        def refresh(self, request):  # noqa: ARG002
            token, expiry = exchange_cursor_oidc()
            self.token = token
            self.expiry = expiry - timedelta(minutes=2)

    creds = _LabWifCredentials()
    creds.refresh(None)
    _wif_creds = creds
    return creds


def _storage_client():
    from google.cloud import storage

    if on_cloud_agent():
        return storage.Client(project=_GCP_PROJECT, credentials=_wif_credentials())
    return storage.Client()


def _blob(uri: str):
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path:
        raise ValueError(f"not a gs:// URI: {uri}")
    return _storage_client().bucket(parsed.netloc).blob(parsed.path.lstrip("/"))


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


def _cmd_mint_oidc() -> int:
    try:
        token, exp = mint_cursor_oidc(_JWT_AUD)
    except Exception as exc:  # noqa: BLE001
        json.dump(
            {
                "version": 1,
                "success": False,
                "code": "401",
                "message": str(exc),
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 1
    json.dump(
        {
            "version": 1,
            "success": True,
            "token_type": "urn:ietf:params:oauth:token-type:id_token",
            "id_token": token,
            "expiration_time": exp,
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


def _cmd_adc() -> int:
    """Print shell exports that point gcloud / ADC at Cursor OIDC WIF.

    No-op (exit 0, no stdout) unless this process is on a Cloud Agent VM.
    """
    if not on_cloud_agent():
        return 0
    cred_path = cache_dir() / "cursor-wif-adc.json"
    command = f"{sys.executable} {Path(__file__).resolve()} mint-oidc"
    config = {
        "type": "external_account",
        "audience": _STS_AUDIENCE,
        "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        "token_url": "https://sts.googleapis.com/v1/token",
        "service_account_impersonation_url": (
            "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
            f"{_LAB_SA}:generateAccessToken"
        ),
        "credential_source": {
            "executable": {
                "command": command,
                "timeout_millis": 10000,
            }
        },
    }
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    cred_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f'export GOOGLE_APPLICATION_CREDENTIALS="{cred_path}"')
    print("export GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES=1")
    print(f'export GOOGLE_CLOUD_PROJECT="{_GCP_PROJECT}"')
    print(f'export CLOUDSDK_CORE_PROJECT="{_GCP_PROJECT}"')
    print(
        f'if command -v gcloud >/dev/null 2>&1; then '
        f'gcloud auth login --cred-file="{cred_path}" --quiet >/dev/null 2>&1 || true; fi'
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: lab_gcs.py <adc|mint-oidc>", file=sys.stderr)
        return 2
    cmd = args[0]
    if cmd == "adc":
        return _cmd_adc()
    if cmd == "mint-oidc":
        return _cmd_mint_oidc()
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
