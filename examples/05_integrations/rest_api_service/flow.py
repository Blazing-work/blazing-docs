import asyncio

from blazing import Blazing
from blazing.base import BaseService


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.service
    class WeatherAPI(BaseService):
        def __init__(self, connectors):
            # In production: self._api_key = connectors.get("weather_api_key")
            self._api_key = "demo-api-key"

        async def get_weather(self, city: str) -> dict:
            """Fetch weather for city (simulated)."""
            # In production:
            # async with httpx.AsyncClient() as client:
            #     response = await client.get(
            #         f"https://api.weather.com/v1/{city}",
            #         headers={"Authorization": f"Bearer {self._api_key}"},
            #     )
            #     return response.json()

            # Simulated weather data
            print(f"[API] Fetching weather for {city}...")
            await asyncio.sleep(0.2)  # Simulate API latency

            weather_data = {
                "New York": {"temp": 72, "conditions": "Sunny"},
                "London": {"temp": 58, "conditions": "Cloudy"},
                "Tokyo": {"temp": 68, "conditions": "Partly Cloudy"},
            }
            return weather_data.get(city, {"temp": 65, "conditions": "Unknown"})

    @app.step
    async def check_weather(city: str, services=None):
        """Check weather for city."""
        weather = await services["WeatherAPI"].get_weather(city)
        return {
            "city": city,
            "temperature": weather["temp"],
            "conditions": weather["conditions"],
        }

    @app.workflow
    async def get_city_weather(city: str, services=None):
        """Workflow: get weather for a city."""
        result = await check_weather(city, services=services)
        return result

    await app.publish()

    # Execute the workflow for multiple cities
    cities = ["New York", "London", "Tokyo"]

    for city in cities:
        print(f"\nChecking weather for {city}...")
        result = await app.get_city_weather(city=city).wait_result()
        print(f"  Temperature: {result['temperature']}°F")
        print(f"  Conditions: {result['conditions']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
