"""Credential-safe, GET-only GitHub token access diagnostic.

Print only coarse status codes. Never print token, response bodies, headers,
repository contents, account identity, or private journal records.
"""
import os
import urllib.error
import urllib.request

API = "https://api.github.com"
PATHS = (("/user", "TOKEN_IDENTITY"), ("/repos/ambani5204/codex-trading-journals", "PRIVATE_REPO"))

def status(token, path, opener=urllib.request.urlopen):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ALGOBANI-Phase0-Auth-Probe",
    })
    try:
        with opener(req, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code

def main():
    token = os.environ.get("JOURNAL_REPO_TOKEN", "")
    if not token:
        print("AUTH_PROBE=BLOCKED reason=SECRET_MISSING", flush=True)
        return 2
    try:
        results = [(label, status(token, path)) for path, label in PATHS]
    except (urllib.error.URLError, TimeoutError, OSError):
        print("AUTH_PROBE=BLOCKED reason=NETWORK_ERROR", flush=True)
        return 3
    for label, code in results:
        print("AUTH_PROBE " + label + " http_status=" + str(code), flush=True)
    if all(code == 200 for _, code in results):
        print("AUTH_PROBE=PASS", flush=True)
        return 0
    print("AUTH_PROBE=BLOCKED reason=TOKEN_OR_REPOSITORY_ACCESS", flush=True)
    return 4

if __name__ == "__main__":
    raise SystemExit(main())
