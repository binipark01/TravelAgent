from travel_agent.app.connectors.mock import MockConnector


def MockSafetyConnector():
    return MockConnector("mock", "safety")


def MofaSafetyConnector():
    return MockConnector("mofa", "safety")
