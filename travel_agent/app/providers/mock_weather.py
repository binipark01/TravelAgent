from __future__ import annotations


class MockWeatherProvider:
    provider_name = "mock_weather"

    def get_weather_summary(self, destination: str) -> str:
        return f"Mock weather for {destination}: seasonal averages only; verify near departure."
