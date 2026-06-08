from travel_agent.app.connectors.mock import MockConnector


def MockRoutesConnector():
    return MockConnector("mock", "route")


def GoogleRoutesConnector():
    return MockConnector("google_routes", "route")


def NaverDirectionsConnector():
    return MockConnector("naver_directions", "route")


def KakaoMobilityConnector():
    return MockConnector("kakao_mobility", "route")
