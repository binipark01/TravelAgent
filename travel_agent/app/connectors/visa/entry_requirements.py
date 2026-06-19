"""대한민국 여권 기준 주요 여행지 입국 요건(무비자 체류일수·전자여행허가·여권 유효기간).

각국 정책은 수시로 바뀌므로 이 데이터는 '출국 전 외교부 해외안전여행/대사관 재확인'을
전제로 한 안내용이다. 모든 항목에 공식 출처 URL을 단다. 라이브 스크래핑이 아닌
큐레이션 레퍼런스이므로 requires_official_verification=True를 유지한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from travel_agent.app.llm import geo_resolver
from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.providers import ProviderMetadata, VisaCheckResult
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now

_MOFA = "https://www.0404.go.kr"  # 외교부 해외안전여행


@dataclass(frozen=True)
class _EntryRule:
    country: str
    visa_required: bool
    visa_free_days: int | None
    entry_authorization: str  # 전자여행허가 등
    passport_validity_rule: str
    notes: list[str] = field(default_factory=list)
    source_url: str = _MOFA


# 대한민국 일반여권 소지자 기준(관광 목적). 변동 가능 → 반드시 공식 확인.
_RULES: dict[str, _EntryRule] = {
    "일본": _EntryRule(
        "일본", False, 90, "전자여행허가 불필요(Visit Japan Web은 입국심사 간소화 선택)",
        "체류 예정 기간 이상의 잔여 유효기간 권장",
        ["무비자 90일(관광)", "Visit Japan Web으로 입국·세관 QR 사전 등록 시 빠름"],
    ),
    "태국": _EntryRule(
        "태국", False, 60, "전자여행허가 불필요(2024.11~ 무비자 60일로 확대)",
        "입국 시 잔여 유효기간 6개월 이상",
        ["무비자 60일(관광)", "출국 항공권·숙소 증빙 요구될 수 있음"],
    ),
    "베트남": _EntryRule(
        "베트남", False, 45, "전자여행허가 불필요(45일 초과 시 e-Visa 필요)",
        "입국 시 잔여 유효기간 6개월 이상",
        ["무비자 45일", "45일 넘게 머물면 e-Visa(전자비자) 사전 신청"],
    ),
    "대만": _EntryRule(
        "대만", False, 90, "전자여행허가 불필요",
        "체류 예정 기간 이상의 잔여 유효기간",
        ["무비자 90일(관광)"],
    ),
    "싱가포르": _EntryRule(
        "싱가포르", False, 90, "SG Arrival Card 온라인 사전 제출 필요",
        "입국 시 잔여 유효기간 6개월 이상",
        ["무비자 90일", "도착 3일 이내 SG Arrival Card 전자 제출 필수"],
    ),
    "홍콩": _EntryRule(
        "홍콩", False, 90, "전자여행허가 불필요",
        "입국 시 잔여 유효기간 1개월 이상",
        ["무비자 90일(관광)"],
    ),
    "필리핀": _EntryRule(
        "필리핀", False, 30, "eTravel(전자입국신고) 등록 필요",
        "입국 시 잔여 유효기간 6개월 이상",
        ["무비자 30일", "출발 72시간 이내 eTravel QR 등록", "왕복 항공권 필요"],
    ),
    "말레이시아": _EntryRule(
        "말레이시아", False, 90, "MDAC(디지털 입국카드) 온라인 사전 제출 필요",
        "입국 시 잔여 유효기간 6개월 이상",
        ["무비자 90일", "도착 3일 이내 MDAC 전자 제출 필수"],
    ),
    "인도네시아": _EntryRule(
        "인도네시아", True, 30, "도착비자(VOA) 또는 e-VOA 필요(유료, 30일·1회 연장 가능)",
        "입국 시 잔여 유효기간 6개월 이상",
        ["무비자 아님 — 도착비자(VOA) 약 50만 루피아", "e-VOA 사전 온라인 발급 가능", "발리 포함"],
    ),
    "미국": _EntryRule(
        "미국", False, 90, "ESTA(전자여행허가) 사전 승인 필수(유료, 약 $21)",
        "체류 기간 + 6개월 권장(입국 시 유효하면 인정)",
        ["VWP 무비자 90일", "출발 전 ESTA 승인 필수 — 미승인 시 탑승 거부"],
    ),
    "괌": _EntryRule(
        "괌", False, 45, "괌-사이판 비자면제(G-CNMI) 45일 / ESTA 있으면 90일",
        "체류 기간 이상의 잔여 유효기간",
        ["무비자 45일(G-CNMI 프로그램)", "I-736 작성 / ESTA 보유 시 더 길게 체류 가능"],
    ),
    "사이판": _EntryRule(
        "사이판", False, 45, "괌-사이판 비자면제(G-CNMI) 45일 / ESTA 있으면 90일",
        "체류 기간 이상의 잔여 유효기간",
        ["무비자 45일(G-CNMI 프로그램)"],
    ),
    "유럽(셰겐)": _EntryRule(
        "유럽(셰겐)", False, 90, "무비자(180일 중 90일) · ETIAS 시행 예정",
        "입국 시 잔여 유효기간 3개월 이상 + 발급 10년 이내",
        ["셰겐 무비자 90일/180일", "ETIAS(전자여행허가) 시행 시 사전 신청 필요"],
    ),
    "영국": _EntryRule(
        "영국", False, 180, "ETA(전자여행허가) 사전 신청 필요",
        "체류 기간 동안 유효",
        ["무비자 6개월(관광)", "ETA 사전 신청 필요(2025 시행)"],
    ),
    "중국": _EntryRule(
        "중국", True, None, "원칙적으로 비자 필요(일부 무비자 시범정책 변동 큼)",
        "입국 시 잔여 유효기간 6개월 이상",
        ["관광 비자 필요(L비자) — 무비자 시범정책은 변동이 커 반드시 확인"],
    ),
    "호주": _EntryRule(
        "호주", True, 90, "ETA(전자비자, 앱 신청) 필요",
        "체류 기간 동안 유효",
        ["ETA 전자비자 사전 신청 필요(무비자 아님)", "1회 체류 최대 90일"],
    ),
    "캐나다": _EntryRule(
        "캐나다", False, 180, "eTA(전자여행허가) 사전 신청 필요(유료, CAD 7)",
        "체류 기간 동안 유효",
        ["무비자 6개월", "항공 입국 시 eTA 필수"],
    ),
}

# 도시·별칭 → 국가(영문/한글 모두 허용, 소문자 비교)
_CITY_TO_COUNTRY: dict[str, str] = {
    # 일본
    "japan": "일본", "일본": "일본", "tokyo": "일본", "도쿄": "일본", "osaka": "일본",
    "오사카": "일본", "sapporo": "일본", "삿포로": "일본", "fukuoka": "일본", "후쿠오카": "일본",
    "okinawa": "일본", "오키나와": "일본", "nagoya": "일본", "나고야": "일본", "kyoto": "일본",
    "교토": "일본",
    # 태국
    "thailand": "태국", "태국": "태국", "bangkok": "태국", "방콕": "태국", "phuket": "태국",
    "푸켓": "태국", "chiang mai": "태국", "치앙마이": "태국",
    # 베트남
    "vietnam": "베트남", "베트남": "베트남", "da nang": "베트남", "danang": "베트남",
    "다낭": "베트남", "hanoi": "베트남", "하노이": "베트남", "ho chi minh": "베트남",
    "호치민": "베트남", "nha trang": "베트남", "나트랑": "베트남", "phu quoc": "베트남",
    "푸꾸옥": "베트남",
    # 대만
    "taiwan": "대만", "대만": "대만", "taipei": "대만", "타이베이": "대만", "타이페이": "대만",
    "taichung": "대만", "가오슝": "대만", "kaohsiung": "대만",
    # 싱가포르/홍콩
    "singapore": "싱가포르", "싱가포르": "싱가포르",
    "hong kong": "홍콩", "hongkong": "홍콩", "홍콩": "홍콩",
    # 필리핀
    "philippines": "필리핀", "필리핀": "필리핀", "manila": "필리핀", "마닐라": "필리핀",
    "cebu": "필리핀", "세부": "필리핀", "boracay": "필리핀", "보라카이": "필리핀",
    # 말레이시아
    "malaysia": "말레이시아", "말레이시아": "말레이시아", "kuala lumpur": "말레이시아",
    "쿠알라룸푸르": "말레이시아", "kota kinabalu": "말레이시아", "코타키나발루": "말레이시아",
    # 인도네시아
    "indonesia": "인도네시아", "인도네시아": "인도네시아", "bali": "인도네시아",
    "발리": "인도네시아", "jakarta": "인도네시아", "자카르타": "인도네시아",
    "denpasar": "인도네시아",
    # 미국/괌/사이판
    "usa": "미국", "united states": "미국", "미국": "미국", "los angeles": "미국", "la": "미국",
    "new york": "미국", "뉴욕": "미국", "hawaii": "미국", "하와이": "미국", "honolulu": "미국",
    "guam": "괌", "괌": "괌", "saipan": "사이판", "사이판": "사이판",
    # 유럽(셰겐)
    "france": "유럽(셰겐)", "프랑스": "유럽(셰겐)", "paris": "유럽(셰겐)", "파리": "유럽(셰겐)",
    "italy": "유럽(셰겐)", "이탈리아": "유럽(셰겐)", "rome": "유럽(셰겐)", "로마": "유럽(셰겐)",
    "spain": "유럽(셰겐)", "스페인": "유럽(셰겐)", "barcelona": "유럽(셰겐)",
    "바르셀로나": "유럽(셰겐)",
    "germany": "유럽(셰겐)", "독일": "유럽(셰겐)", "switzerland": "유럽(셰겐)",
    "스위스": "유럽(셰겐)",
    "netherlands": "유럽(셰겐)", "네덜란드": "유럽(셰겐)",
    # 영국/중국/호주/캐나다
    "uk": "영국", "united kingdom": "영국", "영국": "영국", "london": "영국", "런던": "영국",
    "china": "중국", "중국": "중국", "beijing": "중국", "베이징": "중국", "shanghai": "중국",
    "상하이": "중국",
    "australia": "호주", "호주": "호주", "sydney": "호주", "시드니": "호주",
    "canada": "캐나다", "캐나다": "캐나다", "vancouver": "캐나다", "밴쿠버": "캐나다",
}

_KR_PASSPORT = {"대한민국", "한국", "korea", "south korea", "republic of korea", "kr", "kor"}


def resolve_country(destination: str) -> str | None:
    """도시/국가/별칭 문자열을 데이터셋 국가 키로 정규화한다.

    카탈로그(별칭표)에 없는 도시(시즈오카 등)는 LLM이 국가를 식별한다. 국가 단위 데이터
    (무비자일수·통화·안전·교통패스)는 그 나라 어느 도시든 동일하게 적용되므로 안전하다.
    LLM이 돌려준 국가명도 별칭표로 한 번 더 정규화해 '프랑스'→'유럽(셰겐)' 같은 키로 맞춘다.
    """
    if not destination:
        return None
    text = destination.split(",")[0].strip().lower()
    if text in _CITY_TO_COUNTRY:
        return _CITY_TO_COUNTRY[text]
    # 부분 일치(예: "Tokyo, Japan", "삿포로 여행")
    for alias, country in _CITY_TO_COUNTRY.items():
        if alias in text:
            return country
    resolved = geo_resolver.resolve_place(destination)
    if resolved and resolved.country_ko:
        country_key = resolved.country_ko.strip()
        return _CITY_TO_COUNTRY.get(country_key.lower(), country_key)
    return None


def _metadata(source_url: str) -> ProviderMetadata:
    now = utc_now()
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider="entry_requirements",
        source_url=source_url,
        title="입국 요건(외교부 해외안전여행 기준)",
        reference=f"visa-{now.strftime('%Y%m%d')}",
        retrieved_at=now,
        expires_at=expires_in(24 * 30),
        is_live=False,
        is_mock=False,
        source_type="curated_reference",
        confidence=0.6,
        freshness_note="큐레이션 레퍼런스. 정책은 수시 변동하므로 출국 전 공식 확인 필요.",
    )
    return ProviderMetadata(
        provider_name="entry_requirements",
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(24 * 30),
        normalized_currency=None,
        is_mock=False,
    )


def _is_korean_passport(passport_country: str | None) -> bool:
    if not passport_country:
        return True  # 기본 사용자는 한국 여권으로 가정
    return passport_country.strip().lower() in _KR_PASSPORT


def lookup_entry_requirements(
    destination: str,
    passport_country: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> VisaCheckResult:
    """목적지+국적으로 입국 요건을 조회한다. 데이터가 없으면 보수적 안내를 돌려준다."""
    country = resolve_country(destination)
    metadata = _metadata(_MOFA)

    # 한국 여권이 아니거나 데이터셋에 없는 목적지 → 공식 확인 안내만 제공
    if not _is_korean_passport(passport_country) or country is None or country not in _RULES:
        target = country or destination
        return VisaCheckResult(
            destination_country=target,
            summary=f"{target} 입국 요건은 국적·목적에 따라 달라 공식 출처 확인이 필요합니다.",
            requires_official_verification=True,
            missing_required_info=[] if passport_country else ["passport_country"],
            passport_country=passport_country,
            details=["외교부 해외안전여행에서 국가별 입국 요건을 확인하세요."],
            source_url=_MOFA,
            metadata=metadata,
        )

    rule = _RULES[country]
    details = list(rule.notes)

    # 체류일수 초과 경고
    nights = None
    if start_date and end_date and end_date >= start_date:
        nights = (end_date - start_date).days
    if rule.visa_free_days and nights is not None and nights > rule.visa_free_days:
        details.append(
            f"⚠️ 여행 {nights}일이 무비자 한도({rule.visa_free_days}일)를 초과 — 비자/체류허가 필요"
        )

    if rule.visa_required:
        head = f"{country}: 사전 비자 또는 도착비자 필요"
    elif rule.visa_free_days:
        head = f"{country}: 무비자 {rule.visa_free_days}일(관광)"
    else:
        head = f"{country}: 입국 요건 확인 필요"

    return VisaCheckResult(
        destination_country=country,
        summary=f"{head} · {rule.entry_authorization}",
        requires_official_verification=True,
        missing_required_info=[],
        passport_country=passport_country or "대한민국",
        visa_required=rule.visa_required,
        visa_free_days=rule.visa_free_days,
        entry_authorization=rule.entry_authorization,
        passport_validity_rule=rule.passport_validity_rule,
        details=details,
        source_url=rule.source_url,
        metadata=metadata,
    )
