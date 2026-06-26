from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

from travel_agent.app.connectors import http_fetch


class _FakeResponse(io.BytesIO):
    """urlopen 컨텍스트매니저 흉내(__enter__/__exit__ + read)."""

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _resp(payload: object) -> _FakeResponse:
    return _FakeResponse(json.dumps(payload).encode("utf-8"))


def test_fetch_json_returns_dict_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_fetch, "urlopen", lambda url, timeout: _resp({"ok": 1}))
    assert http_fetch.fetch_json("https://x.example", retries=1) == {"ok": 1}


def test_fetch_json_retries_once_on_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def flaky(url: str, timeout: float):  # noqa: ANN202
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("일시적 연결 실패")
        return _resp({"ok": True})

    monkeypatch.setattr(http_fetch, "urlopen", flaky)
    assert http_fetch.fetch_json("https://x.example", retries=1) == {"ok": True}
    assert calls["n"] == 2  # 첫 시도 실패 → 1회 재시도 후 성공


def test_fetch_json_gives_up_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def always_fail(url: str, timeout: float):  # noqa: ANN202
        calls["n"] += 1
        raise OSError("계속 실패")

    monkeypatch.setattr(http_fetch, "urlopen", always_fail)
    assert http_fetch.fetch_json("https://x.example", retries=1) is None
    assert calls["n"] == 2  # 최초 + 재시도 1회 = 2회 시도 후 포기


def test_fetch_json_no_retry_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def http_500(url: str, timeout: float):  # noqa: ANN202
        calls["n"] += 1
        raise HTTPError(url, 500, "server error", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(http_fetch, "urlopen", http_500)
    assert http_fetch.fetch_json("https://x.example", retries=3) is None
    assert calls["n"] == 1  # HTTPError는 재시도 무의미 → 즉시 폴백


def test_fetch_json_non_dict_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # 최상위가 dict가 아니면(리스트 등) None(호출부는 dict를 기대).
    monkeypatch.setattr(http_fetch, "urlopen", lambda url, timeout: _resp([1, 2, 3]))
    assert http_fetch.fetch_json("https://x.example") is None


def test_fetch_json_invalid_json_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http_fetch, "urlopen", lambda url, timeout: _FakeResponse(b"not-json{{{")
    )
    assert http_fetch.fetch_json("https://x.example") is None
