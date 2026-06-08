from __future__ import annotations

from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field

from travel_agent.app.connectors.flights.naver_browser import (
    NaverBrowserExtractionError,
    NaverFlightBrowserExtractor,
)
from travel_agent.app.schemas.llm import FlightFareCandidate

READ_LIMIT_BYTES = 200_000

KNOWN_FLIGHT_SOURCE_URLS: dict[str, tuple[tuple[str, str], ...]] = {
    "naver_flight": (("flight.naver.com", "/flights/international/"),),
    "skyscanner": (("www.skyscanner.co.kr", "/transport/flights/"),),
    "google_flights": (("www.google.com", "/travel/flights"),),
}


class FlightSourceProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    ok: bool
    verdict: str
    summary: str
    status_code: int | None = None
    body_size: int | None = None
    reasons: list[str] = Field(default_factory=list)
    error: str | None = None
    final_url: str | None = None
    fare_options: list[FlightFareCandidate] = Field(default_factory=list)


class FlightSourceProbeRunner(Protocol):
    def probe(self, source: str, url: str) -> FlightSourceProbeResult: ...


class UnsafeRedirectError(Exception):
    def __init__(self, url: str) -> None:
        super().__init__(f"redirect outside flight source: {url}")
        self.url = url


class SafeFlightRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, source: str) -> None:
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        safe_redirect = safe_flight_redirect_url(
            source=self.source,
            current_url=req.full_url,
            redirect_url=newurl,
        )
        if safe_redirect is None:
            raise UnsafeRedirectError(newurl)
        return super().redirect_request(req, fp, code, msg, headers, safe_redirect)


class PublicFlightSourceProbeRunner:
    def __init__(self, *, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds

    def probe(self, source: str, url: str) -> FlightSourceProbeResult:
        safe_url = safe_flight_source_url(source=source, url=url)
        if safe_url is None:
            return FlightSourceProbeResult(
                source=source,
                ok=False,
                verdict="invalid_source_url",
                summary="항공 검색 source URL 형식과 맞지 않습니다.",
                error="invalid_source_url",
            )
        if source == "naver_flight":
            browser_result = self._probe_naver_browser(source=source, safe_url=safe_url)
            if browser_result is not None:
                return browser_result
        request = Request(
            safe_url,
            headers={"User-Agent": "TravelAgent/0.1 source availability check"},
            method="GET",
        )
        try:
            opener = build_opener(SafeFlightRedirectHandler(source=source))
            with opener.open(request, timeout=self.timeout_seconds) as response:
                final_url = safe_flight_source_url(source=source, url=response.geturl())
                if final_url is None:
                    return _redirect_outside_source(source=source, status_code=response.status)
                body = response.read(READ_LIMIT_BYTES + 1)
                return _result_from_body(
                    source=source,
                    final_url=final_url,
                    status_code=response.status,
                    body=body,
                )
        except HTTPError as exc:
            final_url = safe_flight_source_url(source=source, url=exc.url or safe_url)
            return FlightSourceProbeResult(
                source=source,
                ok=False,
                verdict="restricted_http" if exc.code in {401, 403, 429} else "http_error",
                summary=f"공개 검색 URL이 HTTP {exc.code}로 응답했습니다.",
                status_code=exc.code,
                reasons=["public_url_fetch", "no_browser_automation"],
                final_url=final_url or safe_url,
            )
        except TimeoutError:
            return FlightSourceProbeResult(
                source=source,
                ok=False,
                verdict="timeout",
                summary="공개 검색 URL 확인 시간이 초과되었습니다.",
                error="timeout",
                final_url=safe_url,
            )
        except URLError as exc:
            return FlightSourceProbeResult(
                source=source,
                ok=False,
                verdict="network_error",
                summary="공개 검색 URL 확인에 실패했습니다.",
                error=str(exc.reason),
                final_url=safe_url,
            )
        except UnsafeRedirectError:
            return _redirect_outside_source(source=source, status_code=302)

    def _probe_naver_browser(
        self, *, source: str, safe_url: str
    ) -> FlightSourceProbeResult | None:
        extractor = NaverFlightBrowserExtractor(timeout_seconds=max(self.timeout_seconds, 25))
        try:
            fare_options = extractor.extract(safe_url)
        except NaverBrowserExtractionError:
            return None
        if not fare_options:
            return None
        return FlightSourceProbeResult(
            source=source,
            ok=True,
            verdict="fare_options_found",
            summary=f"Naver 항공권 화면에서 항공권 후보 {len(fare_options)}개를 추출했습니다.",
            status_code=200,
            reasons=["browser_rendered_page", "fare_options_extracted"],
            final_url=safe_url,
            fare_options=fare_options,
        )


def safe_flight_source_url(*, source: str, url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname is None:
        return None
    known_patterns = KNOWN_FLIGHT_SOURCE_URLS.get(source, ())
    if any(
        parsed.hostname == host and parsed.path.startswith(path)
        for host, path in known_patterns
    ):
        return url
    return None


def safe_flight_redirect_url(
    *, source: str, current_url: str, redirect_url: str
) -> str | None:
    return safe_flight_source_url(source=source, url=urljoin(current_url, redirect_url))


def _result_from_body(
    *, source: str, final_url: str, status_code: int, body: bytes
) -> FlightSourceProbeResult:
    if _looks_like_challenge(body):
        return FlightSourceProbeResult(
            source=source,
            ok=False,
            verdict="challenge",
            summary="공개 검색 URL이 자동 접근 제한 화면으로 응답했습니다.",
            status_code=status_code,
            body_size=len(body),
            reasons=["challenge_marker", "public_url_fetch", "no_browser_automation"],
            final_url=final_url,
        )
    return FlightSourceProbeResult(
        source=source,
        ok=200 <= status_code < 400,
        verdict="page_available" if 200 <= status_code < 400 else "http_error",
        summary="공개 항공 검색 URL 응답을 확인했습니다.",
        status_code=status_code,
        body_size=len(body),
        reasons=["public_url_fetch", "no_browser_automation", "public_url_only"],
        final_url=final_url,
    )


def _redirect_outside_source(*, source: str, status_code: int) -> FlightSourceProbeResult:
    return FlightSourceProbeResult(
        source=source,
        ok=False,
        verdict="redirect_outside_source",
        summary="source 범위 밖 URL로 redirect되어 해당 응답은 사용하지 않았습니다.",
        status_code=status_code,
        reasons=["source_url_scope"],
    )


def _looks_like_challenge(body: bytes) -> bool:
    marker_text = body[:READ_LIMIT_BYTES].lower()
    return any(marker in marker_text for marker in [b"captcha", b"/sorry/", b"px-cloud"])
