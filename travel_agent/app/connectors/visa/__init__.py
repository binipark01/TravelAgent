from travel_agent.app.connectors.mock import MockConnector


def MockVisaConnector():
    return MockConnector("mock", "visa")


def SherpaVisaConnector():
    return MockConnector("sherpa", "visa")


def TimaticVisaConnector():
    return MockConnector("timatic", "visa")
