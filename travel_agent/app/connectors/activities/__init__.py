from travel_agent.app.connectors.mock import MockConnector


def MockActivityConnector():
    return MockConnector("mock", "activity")


def ViatorActivityConnector():
    return MockConnector("viator", "activity")


def GetYourGuideActivityConnector():
    return MockConnector("getyourguide", "activity")
