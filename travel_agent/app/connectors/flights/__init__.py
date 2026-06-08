from travel_agent.app.connectors.mock import MockConnector


def MockFlightConnector():
    return MockConnector("mock", "flight")


def AmadeusFlightConnector():
    return MockConnector("amadeus", "flight")


def SkyscannerFlightConnector():
    return MockConnector("skyscanner", "flight")


def NaverFlightConnector():
    return MockConnector("naver_flight", "flight")
