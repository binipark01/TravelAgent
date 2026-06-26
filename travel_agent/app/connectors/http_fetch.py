"""키 불필요 공개 API용 공통 JSON fetch 유틸(transient 재시도 + 표준 로깅).

FX·날씨처럼 단발 urlopen으로 JSON을 받는 커넥터가 공유한다. 일시적 네트워크 블립
(OSError)은 1회 재시도하고, 그래도 실패하면 None을 돌려준다 — 호출부의 기존 폴백
(None/기본값) 동작·shape는 그대로 둔다. 실패는 logging으로만 남겨(동작 불변) "왜
환율/날씨가 비었나"를 추적할 수 있게 한다.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError
from urllib.request import urlopen

logger = logging.getLogger(__name__)


def fetch_json(url: str, *, timeout: float = 8.0, retries: int = 1) -> dict | None:
    """url에서 JSON 객체를 받아 dict로 돌려준다. 실패하면 None(best-effort).

    transient OSError(연결 끊김·DNS 블립 등)는 retries회 더 시도한다. HTTPError(4xx/5xx)나
    JSON 파싱 실패(ValueError)는 재시도해도 같으니 즉시 None. 결과 최상위가 dict가 아니면
    None(호출부는 dict를 기대).
    """
    attempts = max(retries, 0) + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(url, timeout=timeout) as response:  # noqa: S310 - 신뢰된 공개 API URL
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # 4xx/5xx는 재시도해도 동일 → 즉시 폴백.
            logger.info("fetch_json HTTP 오류 url=%s status=%s", url, exc.code)
            return None
        except ValueError as exc:
            # JSON 파싱 실패도 재시도 무의미.
            logger.info("fetch_json JSON 파싱 실패 url=%s err=%s", url, exc)
            return None
        except OSError as exc:
            # 연결/타임아웃 등 일시적일 수 있는 실패 → 남은 시도가 있으면 재시도.
            last_error = exc
            if attempt + 1 < attempts:
                logger.debug(
                    "fetch_json 일시적 실패 url=%s attempt=%d/%d err=%s",
                    url, attempt + 1, attempts, exc,
                )
                continue
            logger.info("fetch_json 최종 실패 url=%s err=%s", url, exc)
            return None
        if not isinstance(data, dict):
            logger.info("fetch_json 응답이 dict가 아님 url=%s type=%s", url, type(data).__name__)
            return None
        return data
    # 도달하지 않지만 방어적으로.
    if last_error is not None:
        logger.info("fetch_json 실패 url=%s err=%s", url, last_error)
    return None
