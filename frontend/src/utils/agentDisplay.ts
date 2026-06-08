export function agentDisplayLabel(agentName: string): string {
  const labels: Record<string, string> = {
    IntakeAgent: '요청 분석',
    DestinationDiscoveryAgent: '목적지 후보 탐색',
    FlightAgent: '항공권 검색',
    AccommodationAgent: '숙소 후보 탐색',
    RestaurantAgent: '맛집/식당 후보 탐색',
    RouteAgent: '동선 최적화',
    BudgetAgent: '예산 계산',
    PlanCriticAgent: '일정 검증',
    PresentationAgent: '최종 계획 정리',
    // 과거 실행 기록 호환용 (구 이름)
    TransportAgent: '항공권 검색',
    POIExperienceAgent: '맛집/식당 후보 탐색',
    RouteOptimizationAgent: '동선 최적화',
    VisaRiskAgent: '입국 리스크 확인',
  }

  return labels[agentName] ?? agentName.replace(/Agent$/, '')
}

export function toolCallDisplayLabel(call: Record<string, unknown>): string {
  const rawTool = String(call.tool ?? '')
  const labels: Record<string, string> = {
    'FlightProvider.search_flights': '항공 후보 조회',
    'AccommodationProvider.search_accommodations': '숙소 후보 조회',
    'AccommodationSearchTool.search': '숙소 source 조회',
    'PlacesProvider.search_pois': '현지 장소 후보 조회',
    'RoutesProvider.compute_route_matrix': '동선 이동시간 계산',
    'VisaProvider.check_entry_requirements': '입국 요건 확인',
  }

  return labels[rawTool] ?? '외부 정보 조회'
}
