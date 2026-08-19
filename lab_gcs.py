"""Resolve large workstation assets from a private lab GCS bucket.

Local files win when present. Otherwise ``lab_assets.json`` (repo root) maps
repo-relative paths to ``gs://`` URIs. JSON/CSV should be streamed; weights
may be downloaded to ``~/.cache/lab-gcs`` (outside the repo).

On a Cursor Cloud Agent / Cursor Web VM, GCS uses Workload Identity Federation:
mint a short-lived OIDC JWT from ``CURSOR_AGENT_SOCKET``, exchange it at STS,
and impersonate ``cursor-lab-reader`` (lab buckets only). Laptops keep using ADC.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any, Optional
from urllib.error import HTTPError, URLError
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
    unresolved = Path(path)
    try:
        p = p.resolve()
    except OSError:
        p = unresolved
    root = (root or find_root(p if p.exists() else Path.cwd())).resolve()
    mapping = _load_map(root)
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        rel = unresolved.as_posix().lstrip("./")
    if rel in mapping:
        return mapping[rel]
    prefixes = sorted(
        (k for k in mapping if rel == k or rel.startswith(k.rstrip("/") + "/")),
        key=len,
        reverse=True,
    )
    if prefixes:
        key = prefixes[0]
        base = mapping[key].rstrip("/")
        rest = rel[len(key.rstrip("/")) :].lstrip("/")
        return f"{base}/{rest}" if rest else base
    if p.name in mapping:
        return mapping[p.name]
    return mapping.get(unresolved.as_posix().lstrip("./"))


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
        if sock.exists():
            return True
    except OSError:
        pass
    return bool(os.environ.get("CURSOR_AGENT_SOCKET"))


def wait_for_agent_socket(timeout_s: float = 20.0) -> Path:
    sock = agent_socket_path()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if sock.exists():
                return sock
        except OSError:
            pass
        time.sleep(0.25)
    raise RuntimeError(
        f"Cursor OIDC socket not found at {sock}. "
        "This helper only federates on a Cursor Cloud Agent / Cursor Web VM."
    )


def _unix_http_json(method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    sock_path = str(wait_for_agent_socket())
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
        raise RuntimeError(f"Cursor OIDC mint failed ({status_line}): {rest[:800]!r}")
    if rest.startswith(b"{"):
        return json.loads(rest.decode("utf-8"))
    # Chunked or other framing: last JSON object in the body.
    text = rest.decode("utf-8", errors="replace")
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise RuntimeError(f"Cursor OIDC mint returned non-JSON: {text[:300]!r}")


def _mint_via_curl(audience: str) -> dict[str, Any]:
    sock_path = str(wait_for_agent_socket())
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "--unix-socket",
            sock_path,
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"aud": audience}),
            "http://cursor-agent/v1/tokens/oidc",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"curl OIDC mint failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout[:400]}"
        )
    return json.loads(proc.stdout)


def mint_cursor_oidc(audience: str = _JWT_AUD) -> tuple[str, int]:
    """Return (jwt, expires_at_unix). Tokens last 5 minutes; cache until expiry."""
    errors: list[str] = []
    data: dict[str, Any] | None = None
    for fn in (_mint_via_curl, lambda aud: _unix_http_json("POST", "/v1/tokens/oidc", {"aud": aud})):
        try:
            data = fn(audience)
            break
        except FileNotFoundError as exc:
            errors.append(str(exc))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")
    if data is None:
        raise RuntimeError("Cursor OIDC mint failed: " + " | ".join(errors))
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
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1500]
        raise RuntimeError(f"GCP token exchange failed for {url}: HTTP {exc.code} {body}") from exc
    except URLError as exc:
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


def _ensure_gcs_lib() -> None:
    try:
        import google.cloud.storage  # noqa: F401
        return
    except ImportError:
        pass
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--user", "google-cloud-storage>=2.14"],
        timeout=180,
    )


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
    _ensure_gcs_lib()
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
    if os.environ.get("LAB_GCS_CACHE"):
        return Path(os.environ["LAB_GCS_CACHE"])
    if on_cloud_agent():
        return Path("/tmp/lab-gcs")
    return Path.home() / ".cache" / "lab-gcs"


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


def _jwt_claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    pad = "=" * ((4 - len(payload) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(payload + pad))


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
    print("export LAB_GCS_CACHE=/tmp/lab-gcs")
    print(
        f'if command -v gcloud >/dev/null 2>&1; then '
        f'gcloud auth login --cred-file="{cred_path}" --quiet >/dev/null 2>&1 || true; fi'
    )
    return 0


def _cmd_pull() -> int:
    """Download mapped lab files (not FitRec-scale dumps) to their repo-relative paths."""
    root = find_root()
    mapping = _load_map(root)
    if not mapping:
        print("no lab_assets.json mappings", file=sys.stderr)
        return 1
    pulled = 0
    for rel, uri in mapping.items():
        if "endomondoHR" in rel or "endomondoHR" in uri:
            print(f"skip huge {rel}", file=sys.stderr)
            continue
        parsed = urlparse(uri)
        name = Path(parsed.path).name
        if not name or "." not in name:
            print(f"skip prefix {rel} -> {uri}", file=sys.stderr)
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        out = ensure_file(rel, dest=dest)
        print(out)
        pulled += 1
    return 0 if pulled else 1


def _cmd_probe() -> int:
    sock = agent_socket_path()
    print(f"socket={sock}")
    print(f"CURSOR_AGENT_SOCKET={os.environ.get('CURSOR_AGENT_SOCKET', '')}")
    print(f"exists={sock.exists() if True else False}")
    print(f"on_cloud_agent={on_cloud_agent()}")
    if not on_cloud_agent():
        print("not a Cloud Agent VM; laptop ADC is used instead of WIF")
        return 0
    token, exp = mint_cursor_oidc(_JWT_AUD)
    claims = _jwt_claims(token)
    interesting = {
        k: claims.get(k)
        for k in (
            "iss",
            "sub",
            "aud",
            "agent_runtime",
            "owner_email",
            "owner_user_id",
            "repo_url",
            "exp",
        )
    }
    print(f"oidc_exp={exp}")
    print(f"oidc_claims={json.dumps(interesting, ensure_ascii=False)}")
    access, expiry = exchange_cursor_oidc()
    print(f"sa_token_len={len(access)} sa_expiry={expiry.isoformat()}Z")
    uri = gcs_uri_for(".cursor-wif-probe.txt") or gcs_uri_for("data/.cursor-wif-probe.txt")
    if not uri:
        mapping = _load_map(find_root())
        uri = next(iter(mapping.values()), None)
    if not uri:
        print("no lab_assets.json mapping to probe")
        return 1
    blob = _blob(uri)
    blob.reload()
    print(f"gcs_ok uri={uri} size={blob.size}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: lab_gcs.py <adc|mint-oidc|probe|pull>", file=sys.stderr)
        return 2
    cmd = args[0]
    if cmd == "adc":
        return _cmd_adc()
    if cmd == "mint-oidc":
        return _cmd_mint_oidc()
    if cmd == "pull":
        return _cmd_pull()
    if cmd == "probe":
        return _cmd_probe()
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
