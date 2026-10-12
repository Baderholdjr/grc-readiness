"""Document stores: the client's controlled documents exist where they say, and are kept current.

SharePoint / OneDrive (Microsoft Graph, app-only):
  MS_TENANT_ID, MS_CLIENT_ID (repository variables), MS_CLIENT_SECRET (secret).
  The app registration needs the read-only application permission Sites.Read.All (or Sites.Selected).
Google Drive:
  Uses the GCP sign-in already used for cloud checks (google-github-actions/auth); the service
  account must be given Viewer access to the folder (or the shared drive). Needs the google-auth package.

Snapshots record names, dates, versions and links only - never document content.
"""
from __future__ import annotations

import urllib.parse

from . import http
from .base import FAIL, PASS, CheckResult, MissingCredentials, collector, env, match, parse_time, setting, utcnow

GRAPH = "https://graph.microsoft.com/v1.0"
DRIVE = "https://www.googleapis.com/drive/v3"


def evaluate(store: str, files: list[dict], names: list[str] | None, max_age_days: int | None,
             require_major_version: bool = False) -> CheckResult:
    """files: [{name, modified (datetime), version, url}]. Each wanted name must match a file (substring)."""
    now = utcnow()
    findings, rows = [], []
    selected = files if not names else [f for f in files if match(f["name"], names)]
    if names:
        for w in names:
            if not any(match(f["name"], [w]) for f in files):
                findings.append(f"no document matching '{w}' in {store}")
    for f in selected:
        age = (now - f["modified"]).days if f.get("modified") else None
        rows.append({"name": f["name"], "modified": f["modified"].date().isoformat() if f.get("modified") else None,
                     "age_days": age, "version": f.get("version"), "url": f.get("url")})
        if max_age_days is not None and (age is None or age > max_age_days):
            findings.append(f"'{f['name']}' last changed {rows[-1]['modified'] or 'never'}, more than {max_age_days} days ago")
        if require_major_version and f.get("version") is not None and not str(f["version"]).endswith(".0"):
            findings.append(f"'{f['name']}' latest version {f['version']} is a draft (minor) version, not a published one")
    return CheckResult(FAIL if findings else PASS, f"{len(rows)} document(s) checked in {store}",
                       {"store": store, "count": len(rows), "items": [r["name"] for r in rows], "documents": rows}, findings)


# ------------------------------------------------------------------ Microsoft Graph
def _graph_token() -> str:
    tenant = setting("MS_TENANT_ID")
    resp = http.request("POST", f"https://login.microsoftonline.com/{urllib.parse.quote(tenant)}/oauth2/v2.0/token",
                        form={"client_id": setting("MS_CLIENT_ID"), "client_secret": env("MS_CLIENT_SECRET"),
                              "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"})
    tok = (resp or {}).get("access_token")
    if not tok:
        raise MissingCredentials("Microsoft Graph returned no access token")
    return tok


def _graph_all(url: str, headers: dict, limit: int = 2000) -> list[dict]:
    items = []
    while url and len(items) < limit:
        page = http.request("GET", url, headers=headers) or {}
        items.extend(page.get("value") or [])
        url = page.get("@odata.nextLink")
    return items[:limit]


@collector("sharepoint.documents")
def sharepoint_documents(site: str, folder: str = "", library: str = "Documents", names: list[str] | None = None,
                         max_age_days: int | None = None, require_major_version: bool = False) -> CheckResult:
    """Named documents exist in a SharePoint library folder and were changed within max_age_days.

    site: "contoso.sharepoint.com:/sites/AIMS" (hostname:/server-relative path).
    require_major_version: the latest version is published (e.g. 3.0), not a draft (3.1).
    """
    h = {"Authorization": f"Bearer {_graph_token()}", "Accept": "application/json"}
    host, _, path = site.partition(":")
    s = http.request("GET", f"{GRAPH}/sites/{host}:{path or '/'}", headers=h) or {}
    drives = _graph_all(f"{GRAPH}/sites/{s.get('id')}/drives", h)
    drive = next((d for d in drives if str(d.get("name", "")).lower() == library.lower()), None)
    if not drive:
        return CheckResult(FAIL, f"library '{library}' not found on {site}", {"site": site, "items": []},
                           [f"document library '{library}' not found on {site}"])
    base = f"{GRAPH}/drives/{drive['id']}"
    loc = f"{base}/root:/{urllib.parse.quote(folder.strip('/'))}:/children" if folder.strip("/") else f"{base}/root/children"
    files = []
    for it in _graph_all(loc, h):
        if "file" not in it:
            continue
        version = None
        if require_major_version:
            vs = (http.request("GET", f"{base}/items/{it['id']}/versions", headers=h) or {}).get("value") or []
            version = vs[0].get("id") if vs else None
        files.append({"name": it.get("name", ""), "modified": parse_time(it.get("lastModifiedDateTime")),
                      "version": version, "url": it.get("webUrl")})
    return evaluate(f"SharePoint {site}/{library}/{folder}".rstrip("/"), files, names, max_age_days, require_major_version)


# ------------------------------------------------------------------ Google Drive
def _google_token() -> str:
    from .. import sandbox
    if sandbox.active():
        return "sandbox"
    try:
        import google.auth
        import google.auth.transport.requests
    except ImportError as exc:
        raise MissingCredentials("google-auth is not installed") from exc
    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
        creds.refresh(google.auth.transport.requests.Request())
    except Exception as exc:  # DefaultCredentialsError, RefreshError
        raise MissingCredentials(f"no Google credentials ({type(exc).__name__})") from exc
    return creds.token


@collector("gdrive.documents")
def gdrive_documents(folder_id: str, names: list[str] | None = None, max_age_days: int | None = None) -> CheckResult:
    """Named documents exist in a Google Drive folder (or shared drive folder) and are current."""
    h = {"Authorization": f"Bearer {_google_token()}", "Accept": "application/json"}
    if not folder_id.replace("-", "").replace("_", "").isalnum():
        return CheckResult(FAIL, "invalid folder id", {"items": []}, ["folder_id must be a Drive folder id"])
    files, token = [], None
    while len(files) < 2000:
        params = {"q": f"'{folder_id}' in parents and trashed = false", "pageSize": 200,
                  "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,version,webViewLink)",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if token:
            params["pageToken"] = token
        page = http.request("GET", f"{DRIVE}/files", headers=h, params=params) or {}
        for f in page.get("files") or []:
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            files.append({"name": f.get("name", ""), "modified": parse_time(f.get("modifiedTime")),
                          "version": None, "url": f.get("webViewLink")})
        token = page.get("nextPageToken")
        if not token:
            break
    return evaluate(f"Google Drive folder {folder_id}", files, names, max_age_days)
