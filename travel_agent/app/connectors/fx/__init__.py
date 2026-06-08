from travel_agent.app.connectors.mock import MockConnector


def MockFxConnector():
    return MockConnector("mock", "fx")


def FrankfurterFxConnector():
    return MockConnector("frankfurter", "fx")


def OpenExchangeRatesConnector():
    return MockConnector("open_exchange_rates", "fx")
