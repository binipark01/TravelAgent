"""실시간 환율(open.er-api.com, 키 불필요)로 예산을 현지통화로 환산한다.

목적지 → 통화 매핑은 비자 커넥터의 도시→국가 정규화를 재사용한다.
API 실패 시 None을 반환해 화면에서 조용히 생략한다(절대 가짜 환율을 쓰지 않음).
"""

from __future__ import annotations

import logging

from travel_agent.app.connectors.http_fetch import fetch_json
from travel_agent.app.connectors.visa.entry_requirements import resolve_country
from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.providers import FxInfo, FxSample, ProviderMetadata
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now

logger = logging.getLogger(__name__)

_API = "https://open.er-api.com/v6/latest"
_TIMEOUT = 8

# 국가 → 통화코드
_COUNTRY_CCY: dict[str, str] = {
    "일본": "JPY", "태국": "THB", "베트남": "VND", "대만": "TWD", "싱가포르": "SGD",
    "홍콩": "HKD", "필리핀": "PHP", "말레이시아": "MYR", "인도네시아": "IDR",
    "미국": "USD", "괌": "USD", "사이판": "USD", "유럽(셰겐)": "EUR", "영국": "GBP",
    "중국": "CNY", "호주": "AUD", "캐나다": "CAD",
    # 유로존 개별국 — resolve_country가 '유럽(셰겐)'으로 안 묶고 개별국으로 풀 때 환율이
    # None이 되지 않게(비엔나·리스본 '환율없음' 버그). 영문 별칭도 함께.
    "프랑스": "EUR", "France": "EUR", "독일": "EUR", "Germany": "EUR",
    "이탈리아": "EUR", "Italy": "EUR", "스페인": "EUR", "Spain": "EUR",
    "네덜란드": "EUR", "Netherlands": "EUR", "오스트리아": "EUR", "Austria": "EUR",
    "포르투갈": "EUR", "Portugal": "EUR", "그리스": "EUR", "벨기에": "EUR",
    "아일랜드": "EUR", "핀란드": "EUR",
    # 셰겐이지만 유로가 아닌 나라 — '유럽(셰겐)'→EUR로 묶이면 틀린다(취리히 CHF, 프라하 CZK).
    "스위스": "CHF", "Switzerland": "CHF", "체코": "CZK", "Czech": "CZK", "Czechia": "CZK",
}

# 셰겐이라도 유로가 아닌 유럽 도시/국가 — resolve_country가 '유럽(셰겐)'으로 묶기 전에 도시·
# 국가명으로 먼저 통화를 잡는다(아래 키워드가 destination에 있으면 그 통화 강제).
_NON_EURO_EUROPE: list[tuple[tuple[str, ...], str]] = [
    (("스위스", "switzerland", "취리히", "zurich", "zürich", "제네바", "geneva", "바젤"), "CHF"),
    (("체코", "czech", "프라하", "prague", "praha"), "CZK"),
    (("헝가리", "hungary", "부다페스트", "budapest"), "HUF"),
    (("폴란드", "poland", "바르샤바", "warsaw", "크라쿠프", "krakow"), "PLN"),
    (("스웨덴", "sweden", "스톡홀름", "stockholm"), "SEK"),
    (("노르웨이", "norway", "오슬로", "oslo"), "NOK"),
    (("덴마크", "denmark", "코펜하겐", "copenhagen"), "DKK"),
]

# 통화별 표기 이름과 샘플 단위(현지통화 기준)
_CURRENCY_META: dict[str, dict] = {
    "JPY": {"name": "엔", "samples": [1000, 10000]},
    "THB": {"name": "밧", "samples": [100, 1000]},
    "VND": {"name": "동", "samples": [100000, 500000]},
    "TWD": {"name": "대만달러", "samples": [100, 1000]},
    "SGD": {"name": "싱가포르달러", "samples": [10, 100]},
    "HKD": {"name": "홍콩달러", "samples": [100, 1000]},
    "PHP": {"name": "페소", "samples": [500, 5000]},
    "MYR": {"name": "링깃", "samples": [50, 500]},
    "IDR": {"name": "루피아", "samples": [100000, 1000000]},
    "USD": {"name": "달러", "samples": [10, 100]},
    "EUR": {"name": "유로", "samples": [10, 100]},
    "GBP": {"name": "파운드", "samples": [10, 100]},
    "CNY": {"name": "위안", "samples": [100, 1000]},
    "AUD": {"name": "호주달러", "samples": [10, 100]},
    "CAD": {"name": "캐나다달러", "samples": [10, 100]},
    "CHF": {"name": "스위스프랑", "samples": [10, 100]},
    "CZK": {"name": "코루나", "samples": [100, 1000]},
    "HUF": {"name": "포린트", "samples": [1000, 10000]},
    "PLN": {"name": "즈워티", "samples": [10, 100]},
    "SEK": {"name": "스웨덴크로나", "samples": [100, 1000]},
    "NOK": {"name": "노르웨이크로네", "samples": [100, 1000]},
    "DKK": {"name": "덴마크크로네", "samples": [100, 1000]},
}

_TIPS_COMMON = [
    "공항 환전소는 환율이 가장 불리 — 시내 은행/사설환전소나 현지 ATM 이용",
    "트래블월렛·토스·트래블로그 같은 외화 충전식 카드가 환율·수수료에 유리",
]
_TIPS_BY_CCY: dict[str, list[str]] = {
    "JPY": ["엔화는 국내 주거래은행 환전 우대가 큼", "현금 사회 — 소액 현금 + 교통IC 충전 권장"],
    "VND": ["동(VND)은 0이 많아 단위 주의", "현지 금은방 환율이 은행보다 유리한 편"],
    "THB": ["밧은 현지 SuperRich 등 사설환전소 환율이 좋음"],
    "USD": ["달러는 국내에서 미리 환전, 팁 문화 대비 소액권 확보"],
    "IDR": ["루피아는 0이 많음 — 공인 환전소(PVA Berizin)만 이용"],
}


def destination_currency(destination: str) -> str | None:
    # 비유로존 유럽(셰겐이라도 통화가 다름)은 도시·국가명으로 먼저 잡는다 — resolve_country가
    # '유럽(셰겐)'으로 묶으면 EUR로 잘못 가기 때문(취리히 CHF, 프라하 CZK 등).
    low = (destination or "").lower()
    for keys, ccy in _NON_EURO_EUROPE:
        if any(k in low for k in keys):
            return ccy
    country = resolve_country(destination)
    if country is None:
        return None
    return _COUNTRY_CCY.get(country)


def _fetch_rate(base: str, target: str) -> float | None:
    """1 base = ? target (open.er-api). transient 실패는 1회 재시도(fetch_json)."""
    data = fetch_json(f"{_API}/{base}", timeout=_TIMEOUT, retries=1)
    if data is None:
        return None
    if data.get("result") != "success":
        logger.info("FX 응답 result!=success base=%s target=%s", base, target)
        return None
    rate = (data.get("rates") or {}).get(target)
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        logger.info("FX rate 파싱 실패 base=%s target=%s raw=%r", base, target, rate)
        return None
    return rate if rate > 0 else None


def _won(amount: float) -> str:
    return f"약 {round(amount):,}원"


def _local_label(amount: int, name: str) -> str:
    return f"{amount:,}{name}"


def _metadata(source_url: str) -> ProviderMetadata:
    now = utc_now()
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider="fx_rate",
        source_url=source_url,
        title="실시간 환율(open.er-api.com)",
        reference=f"fx-{now.strftime('%Y%m%d%H%M')}",
        retrieved_at=now,
        expires_at=expires_in(12),
        is_live=True,
        is_mock=False,
        source_type="public_api",
        confidence=0.7,
        freshness_note="실시간 참고 환율. 실제 환전·결제 환율과 차이 있음.",
    )
    return ProviderMetadata(
        provider_name="fx_rate",
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(12),
        normalized_currency=None,
        is_mock=False,
    )


def fetch_fx_info(
    destination: str,
    base_currency: str = "KRW",
    budget_total_base: float | None = None,
) -> FxInfo | None:
    """목적지 통화로의 실시간 환율과 예산 환산을 돌려준다. 실패 시 None."""
    target = destination_currency(destination)
    if target is None or target == base_currency:
        return None
    target_per_base = _fetch_rate(base_currency, target)
    if target_per_base is None:
        return None
    base_per_target = 1.0 / target_per_base

    meta_ccy = _CURRENCY_META.get(target, {"name": target, "samples": [100, 1000]})
    samples = [
        FxSample(
            local_label=_local_label(unit, meta_ccy["name"]),
            krw_label=_won(unit * base_per_target),
        )
        for unit in meta_ccy["samples"]
    ]

    budget_total_target = None
    budget_total_target_label = None
    if budget_total_base and budget_total_base > 0:
        budget_total_target = budget_total_base * target_per_base
        budget_total_target_label = f"{round(budget_total_target):,} {target}"

    tips = list(_TIPS_COMMON) + _TIPS_BY_CCY.get(target, [])

    return FxInfo(
        base_currency=base_currency,
        target_currency=target,
        target_per_base=target_per_base,
        base_per_target=base_per_target,
        samples=samples,
        budget_total_base=budget_total_base,
        budget_total_target=budget_total_target,
        budget_total_target_label=budget_total_target_label,
        tips=tips,
        source_url="https://www.google.com/search?q=" + f"{base_currency}+{target}+환율",
        metadata=_metadata(f"{_API}/{base_currency}"),
    )
