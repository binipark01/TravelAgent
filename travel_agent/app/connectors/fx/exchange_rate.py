"""실시간 환율(open.er-api.com, 키 불필요)로 예산을 현지통화로 환산한다.

목적지 → 통화 매핑은 비자 커넥터의 도시→국가 정규화를 재사용한다.
API 실패 시 None을 반환해 화면에서 조용히 생략한다(절대 가짜 환율을 쓰지 않음).
"""

from __future__ import annotations

import json
from urllib.request import urlopen

from travel_agent.app.connectors.visa.entry_requirements import resolve_country
from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.providers import FxInfo, FxSample, ProviderMetadata
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now

_API = "https://open.er-api.com/v6/latest"
_TIMEOUT = 8

# 국가 → 통화코드
_COUNTRY_CCY: dict[str, str] = {
    "일본": "JPY", "태국": "THB", "베트남": "VND", "대만": "TWD", "싱가포르": "SGD",
    "홍콩": "HKD", "필리핀": "PHP", "말레이시아": "MYR", "인도네시아": "IDR",
    "미국": "USD", "괌": "USD", "사이판": "USD", "유럽(셰겐)": "EUR", "영국": "GBP",
    "중국": "CNY", "호주": "AUD", "캐나다": "CAD",
}

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
    country = resolve_country(destination)
    if country is None:
        return None
    return _COUNTRY_CCY.get(country)


def _fetch_rate(base: str, target: str) -> float | None:
    """1 base = ? target (open.er-api)."""
    try:
        with urlopen(f"{_API}/{base}", timeout=_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    if (data or {}).get("result") != "success":
        return None
    rate = (data.get("rates") or {}).get(target)
    try:
        rate = float(rate)
    except (TypeError, ValueError):
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
