from __future__ import annotations

from travel_agent.app.schemas.common import CriticFinding, FindingCategory, FindingSeverity
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.time import utc_now


class PlanCriticAgent:
    def run(self, state: TripPlanState) -> TripPlanState:
        findings = list(state.critic_findings)

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
