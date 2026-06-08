from travel_agent.app.connectors.mock import MockConnector


def MockWeatherConnector():
    return MockConnector("mock", "weather")


def OpenMeteoWeatherConnector():
    return MockConnector("open_meteo", "weather")


def OpenWeatherConnector():
    return MockConnector("openweather", "weather")
