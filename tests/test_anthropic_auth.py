"""Signing in to the Anthropic API: an API key, or Workload Identity Federation with GitHub's identity token."""
import pytest

from grc import anthropic_auth as A

FED = {"ANTHROPIC_FEDERATION_RULE_ID": "fdrl_test", "ANTHROPIC_ORGANIZATION_ID": "00000000-0000-0000-0000-000000000000",
       "ANTHROPIC_SERVICE_ACCOUNT_ID": "svac_test"}
GH = {"ACTIONS_ID_TOKEN_REQUEST_URL": "https://pipelines.example.invalid/idtoken?api-version=2.0",
      "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "gh-request-token"}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID", "ANTHROPIC_IDENTITY_TOKEN_FILE", *FED, *GH):
        monkeypatch.delenv(v, raising=False)
    A._cache.clear()


class FakeHttp:
    def __init__(self, fail_exchange=None, expires_in=600):
        self.calls = []
        self.fail_exchange = fail_exchange
        self.expires_in = expires_in

    def request(self, method, url, headers=None, body=None, **kw):
        self.calls.append((method, url, dict(headers or {}), body))
        if method == "GET":
            assert headers["Authorization"] == "Bearer gh-request-token"
            return {"value": f"gh-jwt-{len(self.calls)}"}
        if self.fail_exchange:
            raise RuntimeError(self.fail_exchange)
        return {"access_token": f"sk-ant-oat01-{len(self.calls)}", "expires_in": self.expires_in}


def _set(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_api_key_wins(monkeypatch):
    _set(monkeypatch, ANTHROPIC_API_KEY="sk-ant-api03-x", **FED, **GH)
    http = FakeHttp()
    assert A.method() == "key" and A.headers(http) == {"x-api-key": "sk-ant-api03-x"} and http.calls == []


def test_federation_with_github_identity(monkeypatch):
    _set(monkeypatch, **FED, **GH, ANTHROPIC_WORKSPACE_ID="wrkspc_test")
    http = FakeHttp()
    assert A.method() == "federation"
    assert A.headers(http) == {"authorization": "Bearer sk-ant-oat01-2"}
    get, post = http.calls
    assert get[0] == "GET" and get[1].endswith("&audience=https%3A%2F%2Fapi.anthropic.com")
    assert post[1] == "https://api.anthropic.com/v1/oauth/token"
    assert post[3] == {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": "gh-jwt-1",
                       "federation_rule_id": "fdrl_test", "organization_id": FED["ANTHROPIC_ORGANIZATION_ID"],
                       "service_account_id": "svac_test", "workspace_id": "wrkspc_test"}
    assert A.headers(http) == {"authorization": "Bearer sk-ant-oat01-2"} and len(http.calls) == 2   # cached


def test_short_lived_token_is_refreshed(monkeypatch):
    _set(monkeypatch, **FED, **GH)
    http = FakeHttp(expires_in=10)                      # shorter than the 30 s floor: refreshed after it
    A.headers(http)
    rule = FED["ANTHROPIC_FEDERATION_RULE_ID"]
    A._cache[rule] = (A._cache[rule][0], 0)             # as if it had expired
    assert A.headers(http) == {"authorization": "Bearer sk-ant-oat01-4"} and len(http.calls) == 4


def test_identity_token_file(monkeypatch, tmp_path):
    f = tmp_path / "jwt"
    f.write_text("file-jwt\n")
    _set(monkeypatch, **FED, ANTHROPIC_IDENTITY_TOKEN_FILE=str(f))
    http = FakeHttp()
    A.headers(http)
    assert [c[0] for c in http.calls] == ["POST"] and http.calls[0][3]["assertion"] == "file-jwt"
    assert "workspace_id" not in http.calls[0][3]


def test_refused_exchange_points_to_the_console(monkeypatch):
    _set(monkeypatch, **FED, **GH)
    with pytest.raises(A.AuthUnavailable, match="Authentication history"):
        A.headers(FakeHttp(fail_exchange="HTTP 401: authentication_error"))


def test_nothing_or_partial_configuration_says_what_is_missing(monkeypatch):
    assert A.method() is None and "no Anthropic credentials" in A.missing()
    monkeypatch.setenv("ANTHROPIC_FEDERATION_RULE_ID", "fdrl_x")
    assert "ANTHROPIC_ORGANIZATION_ID" in A.missing()
    _set(monkeypatch, **FED)                            # complete, but no id-token permission
    assert A.method() is None and "id-token: write" in A.missing()
    with pytest.raises(A.AuthUnavailable, match="id-token: write"):
        A.headers(FakeHttp())


def test_tokens_never_appear_in_errors(monkeypatch):
    _set(monkeypatch, **FED, **GH)
    with pytest.raises(A.AuthUnavailable) as e:
        A.headers(FakeHttp(fail_exchange="HTTP 500: upstream"))
    assert "gh-jwt" not in str(e.value) and "gh-request-token" not in str(e.value)


def test_ingest_draft_uses_the_federated_token(monkeypatch):
    from grc.ingest import ai
    _set(monkeypatch, **FED, **GH)
    seen = {}

    class Http(FakeHttp):
        def request(self, method, url, headers=None, body=None, **kw):
            if url == ai.API_URL:
                seen.update(headers)
                return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "{}"}]}
            return super().request(method, url, headers=headers, body=body, **kw)

    monkeypatch.setattr(ai, "http", Http())
    assert ai.draft([("a.txt", "text")], [], [], "Client") == {}
    assert seen["authorization"].startswith("Bearer sk-ant-oat01-") and "x-api-key" not in seen


def test_ingest_without_credentials_reports_why(monkeypatch):
    from grc.ingest import ai
    with pytest.raises(ai.AIUnavailable, match="no Anthropic credentials"):
        ai.draft([("a.txt", "text")], [], [], "Client")
