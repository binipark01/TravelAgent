from __future__ import annotations

import re
from datetime import date, timedelta

from travel_agent.app.agents.llm_client import (
    LLMClient,
    RetryableBriefError,
    StubLLMClient,
)
from travel_agent.app.schemas.brief import IntakeResult, TripBrief


class IntakeAgent:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        enable_live_llm: bool = False,
        llm_max_attempts: int = 2,
    ) -> None:
        self.llm_client = llm_client or StubLLMClient()
        self.enable_live_llm = enable_live_llm
        # LLM을 주력으로 유지: 일시적 실패는 재시도하고, 비싼 타임아웃만 폴백한다.
        self.llm_max_attempts = max(llm_max_attempts, 1)

    def run(
        self,
        message: str,
        *,
        currency: str = "KRW",
        existing_brief: TripBrief | None = None,
        reference_year: int | None = None,
        history: list[str] | None = None,
    ) -> IntakeResult:
        warnings: list[str] = []
        if self.enable_live_llm:
            extracted = self._extract_with_llm_retry(message, currency, history, warnings)
            if extracted is None:
                extracted = self._fallback_parse_with_history(
                    message, currency, reference_year, history
                )
        else:
            extracted = self._fallback_parse_with_history(
                message, currency, reference_year, history
            )

        brief = self._merge_briefs(existing_brief, extracted) if existing_brief else extracted
        self._normalize_trip_dates(brief)
        return IntakeResult(brief=brief, questions=[], warnings=warnings)

    def _extract_with_llm_retry(
        self,
        message: str,
        currency: str,
        history: list[str] | None,
        warnings: list[str],
    ) -> TripBrief | None:
        """LLM 추출을 시도하되 일시적 실패는 재시도한다. 끝내 실패하면 None(→폴백).

        - RetryableBriefError(빈 출력·JSON 깨짐 등): 남은 시도만큼 재시도(저렴).
        - 그 외(타임아웃 등 비싼 실패): 즉시 중단하고 폴백(지연 폭증 방지).
        """
        last_exc: Exception | None = None
        for _ in range(self.llm_max_attempts):
            try:
                return self.llm_client.extract_trip_brief(message, currency, history=history)
            except RetryableBriefError as exc:
                last_exc = exc
                continue  # 일시적 실패 → 재시도
            except Exception as exc:  # noqa: BLE001 - 타임아웃 등은 즉시 폴백
                last_exc = exc
                break
        warnings.append(f"요청 문장을 규칙 기반으로 정리했습니다: {last_exc}")
        return None

    def _normalize_trip_dates(self, brief: TripBrief) -> None:
        """기간(N박)이 명시되면 duration_nights를 맞추고, 종료일이 없으면 채운다.

        날짜 범위(window)는 그대로 둔다. "7월 초~중순 + 4박5일"처럼 범위가 기간보다
        넓으면 FlightAgent가 그 범위 안의 여러 출발일을 검색해 가장 싼 후보를 찾는다.
        """
        if brief.duration_days:
            brief.duration_nights = max(brief.duration_days - 1, 0)
            if brief.start_date and brief.end_date is None:
                brief.end_date = brief.start_date + timedelta(days=brief.duration_nights)

    def _fallback_parse_with_history(
        self,
        message: str,
        currency: str,
        reference_year: int | None,
        history: list[str] | None,
    ) -> TripBrief:
        """규칙 기반 파서도 이전 대화를 누적해 해석한다.

        브라우저의 매 턴은 새 run이라 existing_brief가 비어 있다. LLM이 실패해
        규칙 파서로 떨어지면 history를 무시해 '삿포로 가고싶어 → 4박5일로'에서
        목적지가 사라진다. 과거→현재 순으로 접어 올려(merge) 최신 발화가 이전
        값을 덮어쓰되, 명시하지 않은 항목은 이전 문맥을 유지한다.
        """
        prior = [m for m in (history or []) if m and m.strip()]
        accumulated: TripBrief | None = None
        for past in prior:
            accumulated = self._merge_briefs(
                accumulated, self._fallback_parse(past, currency, reference_year)
            )
        current = self._fallback_parse(message, currency, reference_year)
        return self._merge_briefs(accumulated, current) if accumulated else current

    def _fallback_parse(
        self, message: str, currency: str, reference_year: int | None = None
    ) -> TripBrief:
        text = message.strip()
        year = reference_year or date.today().year
        brief = TripBrief(currency=currency)
        is_flight_search = self._is_flight_search(text)
        brief.origin = self._parse_origin(text)
        brief.destinations = self._parse_destinations(text)
        brief.destination_hint = ", ".join(brief.destinations) if brief.destinations else None
        brief.travelers = self._parse_travelers(text)
        default_origin_assumption = False
        default_traveler_assumption = False
        if is_flight_search and not brief.origin:
            brief.origin = "서울"
            default_origin_assumption = True
        if is_flight_search and brief.travelers is None:
            brief.travelers = 1
            default_traveler_assumption = True
        brief.traveler_count = brief.travelers
        brief.adults = brief.travelers
        brief.duration_days = self._parse_duration_days(text)
        if brief.duration_days:
            brief.duration_nights = max(brief.duration_days - 1, 0)
        start_date, end_date, flexible = self._parse_dates(text, year, brief.duration_days)
        brief.start_date = start_date
        brief.end_date = end_date
        brief.flexible_dates = flexible
        if brief.duration_days is None and start_date and end_date:
            brief.duration_days = (end_date - start_date).days + 1
            brief.duration_nights = max(brief.duration_days - 1, 0)

        budget, per_person = self._parse_budget(text)
        if per_person:
            brief.budget_per_person = budget
            if budget and brief.travelers:
                brief.budget_total = budget * brief.travelers
        else:
            brief.budget_total = budget
            if budget and brief.travelers:
                brief.budget_per_person = budget / brief.travelers

        brief.travel_style = self._parse_style(text)
        brief.pace = self._parse_pace(text)
        brief.accommodation_preference = self._parse_accommodation_preference(text)
        brief.transport_preference = self._parse_transport_preference(text)
        brief.passport_country = self._parse_passport_country(text)
        brief.must_include = self._parse_must_include(text)
        brief.must_avoid = self._parse_must_avoid(text)
        brief.assumptions = self._assumptions(brief, text)
        if default_origin_assumption:
            brief.assumptions.append("출발지가 없어 서울 출발 기준으로 항공 후보를 조회합니다.")
        if default_traveler_assumption:
            brief.assumptions.append("인원이 없어 성인 1명 기준으로 항공 후보를 조회합니다.")
        brief.missing_fields = self._missing_fields(brief)
        return brief

    def _parse_origin(self, text: str) -> str | None:
        explicit = re.search(r"(?:출발지|출발지는|출발은)\s*[:은는]?\s*([가-힣A-Za-z]+)", text)
        if explicit:
            return self._normalize_city(explicit.group(1))
        origin_patterns = {
            "서울": ["서울", "인천", "김포", "Seoul", "ICN", "GMP"],
            "부산": ["부산", "김해", "Busan", "PUS"],
            "대구": ["대구", "Daegu"],
        }
        if any(marker in text for marker in ["출발", "공항", "에서"]):
            for normalized, tokens in origin_patterns.items():
                if any(token in text for token in tokens):
                    return normalized
        return None

    def _parse_destinations(self, text: str) -> list[str]:
        destination_map = {
            "Tokyo": ["도쿄", "동경", "Tokyo", "tokyo"],
            "Osaka": ["오사카", "Osaka", "osaka"],
            "Sapporo": ["삿포로", "홋카이도", "Sapporo", "sapporo", "Hokkaido", "hokkaido"],
            "Fukuoka": ["후쿠오카", "Fukuoka", "fukuoka"],
            "Kyoto": ["교토", "Kyoto", "kyoto"],
            "Japan": ["일본", "Japan", "japan"],
            "Taipei": ["타이베이", "대만", "Taipei", "Taiwan"],
            "Bangkok": ["방콕", "태국", "Bangkok", "Thailand"],
            "Da Nang": ["다낭", "베트남", "Da Nang", "Vietnam"],
        }
        destinations = [
            normalized
            for normalized, tokens in destination_map.items()
            if any(token in text for token in tokens)
        ]
        if "Japan" in destinations and len(destinations) > 1:
            return [destination for destination in destinations if destination != "Japan"]
        return destinations

    def _is_flight_search(self, text: str) -> bool:
        return any(token in text for token in ["항공권", "비행기", "항공편", "비행편", "flight"])

    def _parse_transport_preference(self, text: str) -> str | None:
        preferences: list[str] = []
        if self._is_flight_search(text) or any(token in text for token in ["비행", "항공"]):
            preferences.append("flight")
        if self._is_flight_search(text):
            preferences.append("flight_search")
        compact = re.sub(r"\s+", "", text)
        if any(token in compact for token in ["오전출발", "가는편오전", "출국오전"]):
            preferences.append("outbound_morning")
        if any(token in compact for token in ["오후출발", "돌아오는건오후", "귀국오후"]):
            preferences.append("return_afternoon")
        return ", ".join(dict.fromkeys(preferences)) if preferences else None

    def _parse_travelers(self, text: str) -> int | None:
        match = re.search(r"(?:성인\s*)?(\d+)\s*명", text)
        if match:
            return int(match.group(1))
        if any(token in text for token in ["여자친구", "남자친구", "친구랑", "커플", "둘이"]):
            return 2
        if any(token in text for token in ["혼자", "1인", "나홀로"]):
            return 1
        return None

    def _parse_passport_country(self, text: str) -> str | None:
        match = re.search(r"여권\s*(?:국적|국가)?(?:은|는|:)?\s*([가-힣A-Za-z]+)", text)
        if match:
            return self._normalize_passport_country(match.group(1))
        if any(token in text for token in ["대한민국 여권", "한국 여권", "KR 여권"]):
            return "대한민국"
        return None

    def _parse_duration_days(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*박\s*(\d+)\s*일", text)
        if match:
            return int(match.group(2))
        match = re.search(r"(\d+)\s*일\s*(?:동안|짜리|여행)", text)
        if match:
            return int(match.group(1))
        return None

    def _parse_dates(
        self, text: str, year: int, duration_days: int | None
    ) -> tuple[date | None, date | None, bool]:
        flexible = any(token in text for token in ["초", "중순", "말", "언제든", "유연", "flex"])
        iso_dates = re.findall(r"(20\d{2})-(\d{1,2})-(\d{1,2})", text)
        if len(iso_dates) >= 2:
            first = tuple(map(int, iso_dates[0]))
            second = tuple(map(int, iso_dates[1]))
            return date(*first), date(*second), flexible
        if len(iso_dates) == 1:
            first = date(*tuple(map(int, iso_dates[0])))
            return first, self._end_from_duration(first, duration_days), flexible

        range_match = re.search(
            r"(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*(?:부터|에서|~|-)\s*"
            r"(?:(\d{1,2})\s*월\s*)?(\d{1,2})\s*일?",
            text,
        )
        if range_match:
            start_month = int(range_match.group(1))
            start_day = int(range_match.group(2))
            end_month = int(range_match.group(3) or start_month)
            end_day = int(range_match.group(4))
            start = self._future_date(year, start_month, start_day)
            end = self._future_date(year, end_month, end_day)
            return start, end, flexible

        fuzzy_window_match = re.search(
            r"(\d{1,2})\s*월\s*(초|중순|말)\s*(?:부터|에서|~|-)?\s*(초|중순|말)\s*사이",
            text,
        )
        if fuzzy_window_match:
            month = int(fuzzy_window_match.group(1))
            start_day = {"초": 3, "중순": 11, "말": 21}[fuzzy_window_match.group(2)]
            end_day = {"초": 10, "중순": 15, "말": 28}[fuzzy_window_match.group(3)]
            start = self._future_date(year, month, start_day)
            end = self._future_date(year, month, end_day)
            return start, end, True

        fuzzy_match = re.search(r"(\d{1,2})\s*월\s*(초|중순|말)", text)
        if fuzzy_match:
            month = int(fuzzy_match.group(1))
            anchor_day = {"초": 3, "중순": 12, "말": 22}[fuzzy_match.group(2)]
            start = self._future_date(year, month, anchor_day)
            return start, self._end_from_duration(start, duration_days), True
        return None, None, flexible

    def _parse_budget(self, text: str) -> tuple[float | None, bool]:
        match = re.search(r"(\d+(?:\.\d+)?)\s*만\s*원", text)
        if not match:
            return None, False
        amount = float(match.group(1)) * 10_000
        per_person = any(token in text for token in ["1인", "인당", "per person"])
        return amount, per_person

    def _parse_style(self, text: str) -> str | None:
        styles = []
        style_tokens = {
            "food": ["맛집", "먹방", "음식"],
            "shopping": ["쇼핑", "아울렛"],
            "culture": ["문화", "역사", "박물관"],
            "rest": ["휴양", "쉬고", "온천"],
            "nature": ["자연", "풍경"],
            "activity": ["액티비티", "체험"],
        }
        for style, tokens in style_tokens.items():
            if any(token in text for token in tokens):
                styles.append(style)
        return ", ".join(styles) if styles else None

    def _parse_pace(self, text: str) -> str | None:
        if any(token in text for token in ["여유", "느긋"]):
            return "relaxed"
        if any(token in text for token in ["빡빡", "알차게", "많이"]):
            return "packed"
        return None

    def _parse_accommodation_preference(self, text: str) -> str | None:
        if "교통" in text:
            return "transit first"
        if "위치" in text:
            return "location first"
        if "가격" in text or "저렴" in text:
            return "price first"
        if "호텔" in text:
            return "hotel"
        return None

    def _parse_must_include(self, text: str) -> list[str]:
        includes = []
        for token, value in [
            ("맛집", "food"),
            ("쇼핑", "shopping"),
            ("온천", "onsen"),
            ("자연", "nature"),
            ("역사", "culture"),
        ]:
            if token in text:
                includes.append(value)
        return includes

    def _parse_must_avoid(self, text: str) -> list[str]:
        """대화형 수정: '무리/빡세'(과밀)와 'X 빼줘/제외/말고/싫어'의 X를 모은다."""
        avoid: list[str] = []
        if any(token in text for token in ["무리", "빡세"]):
            avoid.append("overpacked days")
        # "오타루 빼줘", "박물관은 빼고", "미술관 말고", "온천 싫어"의 앞 단어를 잡는다.
        for match in re.finditer(r"([가-힣A-Za-z]{2,})\s*(?:빼|제외|말고|싫|건너)", text):
            token = re.sub(r"(?:은|는|이|가|을|를|도)$", "", match.group(1))
            if len(token) >= 2 and token not in avoid:
                avoid.append(token)
        return avoid

    def _merge_briefs(self, old: TripBrief | None, new: TripBrief) -> TripBrief:
        if old is None:
            return new
        merged = old.model_copy(deep=True)
        scalar_fields = [
            "origin",
            "destination_hint",
            "selected_destination",
            "start_date",
            "end_date",
            "duration_days",
            "duration_nights",
            "traveler_count",
            "adults",
            "children",
            "travelers",
            "budget_total",
            "budget_per_person",
            "travel_style",
            "pace",
            "accommodation_preference",
            "transport_preference",
            "passport_country",
        ]
        for field in scalar_fields:
            value = getattr(new, field)
            if value not in (None, "", []):
                setattr(merged, field, value)
        merged.currency = new.currency or old.currency
        merged.flexible_dates = old.flexible_dates or new.flexible_dates
        for field in [
            "accessibility_needs",
            "dietary_restrictions",
            "must_include",
            "must_avoid",
            "assumptions",
        ]:
            combined = list(dict.fromkeys([*getattr(old, field), *getattr(new, field)]))
            setattr(merged, field, combined)
        # 목적지: 새 발화가 도시를 명시하면 '전환'으로 보고 교체(union하면 옛 도시가 남아
        # 시즈오카를 요청해도 삿포로가 선택돼 버린다). 도시 언급 없으면 이전 목적지 유지.
        if new.destinations:
            merged.destinations = list(dict.fromkeys(new.destinations))
            merged.destination_hint = ", ".join(merged.destinations)
        else:
            merged.destinations = list(old.destinations)
        if merged.traveler_count is None:
            merged.traveler_count = merged.travelers
        if merged.adults is None:
            merged.adults = merged.travelers
        if merged.budget_total is None and merged.budget_per_person and merged.travelers:
            merged.budget_total = merged.budget_per_person * merged.travelers
        if merged.budget_per_person is None and merged.budget_total and merged.travelers:
            merged.budget_per_person = merged.budget_total / merged.travelers
        merged.missing_fields = self._missing_fields(merged)
        return merged

    def _missing_fields(self, brief: TripBrief) -> list[str]:
        missing = []
        if not brief.origin:
            missing.append("origin")
        if not brief.destinations:
            missing.append("destinations")
        if not brief.start_date:
            missing.append("start_date")
        if not brief.end_date:
            missing.append("end_date")
        if not brief.travelers:
            missing.append("travelers")
        is_flight_search = "flight_search" in (brief.transport_preference or "")
        if brief.destinations and not brief.passport_country and not is_flight_search:
            missing.append("passport_country")
        return missing

    def _questions_for_missing(self, missing_fields: list[str]) -> list[str]:
        questions = {
            "origin": "출발지는 어디인가요?",
            "destinations": "가고 싶은 목적지는 어디인가요?",
            "start_date": "출발일 또는 가능한 기간은 언제인가요?",
            "end_date": "귀국일 또는 여행 종료일은 언제인가요?",
            "travelers": "여행 인원은 몇 명인가요?",
            "passport_country": "여권 국적은 어디인가요?",
        }
        return [questions[field] for field in missing_fields if field in questions]

    def _assumptions(self, brief: TripBrief, text: str) -> list[str]:
        assumptions = []
        if brief.destinations == ["Japan"]:
            assumptions.append("일본만 지정되어 도시 후보를 비교한 뒤 선택합니다.")
        if brief.flexible_dates:
            assumptions.append("날짜 표현이 유연하므로 실제 예약 전 정확한 날짜 확인이 필요합니다.")
        if brief.start_date and brief.end_date and "사이" in text:
            assumptions.append(
                "기간 표현은 "
                f"{brief.start_date.isoformat()} ~ {brief.end_date.isoformat()} 범위로 "
                "임시 해석했습니다."
            )
        if brief.start_date and brief.end_date and "초" in text and "사이" not in text:
            assumptions.append(
                "초순 표현은 "
                f"{brief.start_date.isoformat()} ~ {brief.end_date.isoformat()}로 "
                "임시 해석했습니다."
            )
        if not brief.origin:
            assumptions.append("출발지가 없어 항공 후보는 보류하고 현지 일정부터 구성합니다.")
        if not brief.travelers:
            assumptions.append("인원이 없어 1인 기준 예산 추정으로 시작합니다.")
        is_flight_search = "flight_search" in (brief.transport_preference or "")
        if not brief.passport_country and brief.destinations and not is_flight_search:
            assumptions.append("여권 국적이 없어 입국 리스크는 공식 확인 필요 항목으로 표시합니다.")
        return assumptions

    def _normalize_city(self, value: str) -> str:
        value = re.sub(r"(이고|이며|에서|으로|로|은|는|,|\.|\s)+$", "", value)
        if value in {"인천", "김포"}:
            return "서울"
        return value

    def _normalize_passport_country(self, value: str) -> str:
        if value in {"한국", "대한민국", "KR", "KOR", "SouthKorea"}:
            return "대한민국"
        return value

    def _future_date(self, year: int, month: int, day: int) -> date:
        candidate = date(year, month, day)
        today = date.today()
        if candidate < today:
            return date(year + 1, month, day)
        return candidate

    def _end_from_duration(self, start: date, duration_days: int | None) -> date | None:
        if not duration_days:
            return None
        return start + timedelta(days=duration_days - 1)
