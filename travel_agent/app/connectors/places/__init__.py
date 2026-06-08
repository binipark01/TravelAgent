from travel_agent.app.connectors.mock import MockConnector


def MockPlacesConnector():
    return MockConnector("mock", "poi")


def GooglePlacesConnector():
    return MockConnector("google_places", "poi")


def KakaoLocalConnector():
    return MockConnector("kakao_local", "poi")


def KtoTourApiConnector():
    return MockConnector("kto_tourapi", "poi")
