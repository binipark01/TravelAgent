from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, time

from travel_agent.app.schemas.common import CriticFinding, FindingCategory, FindingSeverity
from travel_agent.app.schemas.itinerary import Itinerary
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.time import utc_now

# 결정적 일정 검증 임계값(내부 데이터만 사용 — 외부 fetch 없음). 비자명 값엔 why를 남긴다.
_DAY_END_LIMIT = time(23, 0)  # 하루 마지막 일정이 이 시각을 넘기면 '과late 종료'.
_ACTIVITY_WINDOW_START = time(9, 0)  # 현실적 활동 시작.
_ACTIVITY_WINDOW_END = time(23, 0)  # 현실적 활동 종료.
# 09~23시(14h=840분)를 하루 활동 예산으로 본다. 관광 체류+이동 합이 이를 넘으면 비현실적.
_ACTIVITY_BUDGET_MIN = 840
_SIGHTSEEING_CAP = 6  # 관광 항목이 이 수를 크게 넘으면(>cap) 과밀. 시내 4~5곳 기준의 여유 상한.
# 동선 anchor(공항·숙소/역)는 '관광 곳수'에 세지 않는다 — 이동 출발/도착점이라 부담이 다르다.
_ANCHOR_TYPES = {"공항", "숙소"}


class PlanCriticAgent:
    def run(self, state: TripPlanState) -> TripPlanState:
        findings = list(state.critic_findings)
        # 결정적 일정 실현가능성 검증: 내부 데이터(시간·duration·transfer)로 플래그를 채운다.
        if state.optimized_itinerary:
            self._check_feasibility(state.optimized_itinerary)

        brief = state.brief
        if brief and brief.start_date and brief.end_date and brief.end_date < brief.start_date:
            findings.append(
                CriticFinding(
                    severity=FindingSeverity.blocking,
                    category=FindingCategory.route,
                    message="종료일이 시작일보다 빠릅니다.",
                    suggested_fix="여행 날짜 범위를 다시 입력하세요.",
                )
            )

        if state.optimized_itinerary:
            for day in state.optimized_itinerary.days:
                if len(day.items) > 4:
                    findings.append(
                        CriticFinding(
                            severity=FindingSeverity.warning,
                            category=FindingCategory.route,
                            message=f"{day.day}일차 일정이 과밀합니다.",
                            suggested_fix="하루 주요 POI를 4개 이하로 줄이세요.",
                            affected_plan_items=[item.item_id for item in day.items],
                        )
                    )
                if day.day == 1 and not any("버퍼" in note for note in day.notes):
                    findings.append(
                        CriticFinding(
                            severity=FindingSeverity.warning,
                            category=FindingCategory.route,
                            message="도착일 공항 이동 버퍼가 명시되어 있지 않습니다.",
                            suggested_fix="공항 이동/체크인 버퍼를 추가하세요.",
                        )
                    )

        if (
            state.budget
            and brief
            and brief.budget_total
            and state.budget.total_estimated_cost > brief.budget_total
        ):
            already = any(f.category == FindingCategory.budget for f in findings)
            if not already:
                findings.append(
                    CriticFinding(
                        severity=FindingSeverity.warning,
                        category=FindingCategory.budget,
                        message="예산 초과 가능성이 있습니다.",
                        suggested_fix="무료 활동을 늘리거나 숙소 등급을 낮추세요.",
                    )
                )

        if state.visa_result and state.visa_result.requires_official_verification:
            findings.append(
                CriticFinding(
                    severity=FindingSeverity.warning,
                    category=FindingCategory.visa,
                    message="입국 요건은 mock 요약이며 공식 확인이 필요합니다.",
                    suggested_fix="예약 전 공식 출처 확인을 완료하세요.",
                )
            )

        if not state.source_refs:
            findings.append(
                CriticFinding(
                    severity=FindingSeverity.warning,
                    category=FindingCategory.source_quality,
                    message="source ref가 없어 provider 결과 검증성이 낮습니다.",
                    suggested_fix="provider 응답의 source ref를 상태에 포함하세요.",
                )
            )
        else:
            now = utc_now()
            stale = [
                ref.source_id
                for ref in state.source_refs
                if ref.expires_at and ref.expires_at < now
            ]
            if stale:
                findings.append(
                    CriticFinding(
                        severity=FindingSeverity.warning,
                        category=FindingCategory.source_quality,
                        message="만료된 provider source ref가 있습니다.",
                        suggested_fix="최신 가격/가능 여부를 다시 조회하세요.",
                        affected_plan_items=stale,
                    )
                )

        state.critic_findings = self._dedupe(findings)
        return state

    def _check_feasibility(self, itinerary: Itinerary) -> None:
        """내부 데이터만으로 하루 일정의 실현가능성을 결정적으로 검증해 feasibility_flags를 채운다.

        외부 fetch 없음 — 항상 동작한다. 데이터가 없으면(시간 미상 등) 그 체크는 조용히 통과한다
        (추측 금지). 멱등성: critic이 만든 플래그만 매번 새로 계산해 교체한다(재실행 시 중복 방지).
        """
        # critic이 이전에 넣은 플래그는 걷어내고(접두사로 식별) 비-critic 플래그는 보존한다.
        preserved = [f for f in itinerary.feasibility_flags if not f.startswith("[검증]")]
        generated: list[str] = []
        for day in itinerary.days:
            generated.extend(self._day_feasibility_flags(day))
        # 순서 보존 + 중복 제거.
        seen: set[str] = set()
        merged: list[str] = []
        for flag in [*preserved, *generated]:
            if flag in seen:
                continue
            seen.add(flag)
            merged.append(flag)
        itinerary.feasibility_flags = merged

    def _day_feasibility_flags(self, day) -> list[str]:  # noqa: ANN001 - DayPlan
        flags: list[str] = []
        # 1) 과late 종료: 그날 마지막 일정(관광·식사·이동) 종료가 23시를 넘김.
        latest = self._latest_end_time(day)
        if latest is not None and latest > _DAY_END_LIMIT:
            flags.append(
                f"[검증] {day.day}일차: 마지막 일정이 {latest.strftime('%H:%M')}에 끝나 "
                "너무 늦습니다(23시 이후) — 곳수를 줄이거나 일정을 앞당기세요."
            )
        # 2) 과밀: anchor(공항·숙소)를 뺀 관광 항목 수가 상한을 크게 초과.
        sightseeing = [
            item for item in day.items if (item.type or "") not in _ANCHOR_TYPES
        ]
        if len(sightseeing) > _SIGHTSEEING_CAP:
            flags.append(
                f"[검증] {day.day}일차: 관광 {len(sightseeing)}곳으로 과밀합니다"
                f"(권장 {_SIGHTSEEING_CAP}곳 이하) — 일부를 다른 날로 옮기세요."
            )
        # 3) 시간 예산 비현실: 관광 체류 + 이동 합이 하루 활동창(09~23시, 840분)을 초과.
        used = self._day_minutes_used(day)
        if used > _ACTIVITY_BUDGET_MIN:
            flags.append(
                f"[검증] {day.day}일차: 체류+이동 합계가 약 {used}분으로 하루 활동 가능 시간"
                f"({_ACTIVITY_BUDGET_MIN}분, 09~23시)을 초과합니다 — 일정이 비현실적입니다."
            )
        return flags

    @staticmethod
    def _latest_end_time(day) -> time | None:  # noqa: ANN001 - DayPlan
        """그날 모든 항목(관광·식사·이동)의 가장 늦은 종료 시각. 없으면 None."""
        ends = [item.end_time for item in day.items]
        ends += [meal.end_time for meal in day.meals]
        ends += [xfer.end_time for xfer in day.transfers]
        return max(ends) if ends else None

    @staticmethod
    def _day_minutes_used(day) -> int:  # noqa: ANN001 - DayPlan
        """관광 체류시간 + 이동시간(분)의 합. 식사 시간은 활동창 안에 흡수된다고 보고 제외."""
        total = 0
        for item in day.items:
            total += PlanCriticAgent._minutes_between(item.start_time, item.end_time)
        for xfer in day.transfers:
            # travel_minutes를 우선 신뢰(없거나 0이면 start~end로 보정).
            total += xfer.travel_minutes or PlanCriticAgent._minutes_between(
                xfer.start_time, xfer.end_time
            )
        return total

    @staticmethod
    def _minutes_between(start: time, end: time) -> int:
        """time 두 개 사이 분(자정 넘김은 없다고 보고 음수면 0)."""
        base = date_cls(2026, 1, 1)
        delta = datetime.combine(base, end) - datetime.combine(base, start)
        minutes = int(delta.total_seconds() // 60)
        return max(minutes, 0)

    def _dedupe(self, findings: list[CriticFinding]) -> list[CriticFinding]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[CriticFinding] = []
        for finding in findings:
            key = (finding.severity, finding.category, finding.message)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(finding)
        return deduped
