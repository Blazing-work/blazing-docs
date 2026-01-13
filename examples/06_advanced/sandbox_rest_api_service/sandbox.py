import asyncio

from blazing import Blazing
from blazing.base import BaseService


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # YOUR CODE (trusted - has real API credentials)
    @app.service
    class ExternalAPIService(BaseService):
        def __init__(self, connectors):
            # Real API key (user code NEVER sees this)
            # In production: self._api_key = connectors.get("api_key")
            self._api_key = "demo-secret-api-key"
            self._base_url = "https://api.example.com"

        async def fetch_weather(self, city: str) -> dict:
            """Fetch weather from external API (simulated)."""
            # In production:
            # async with httpx.AsyncClient() as client:
            #     response = await client.get(
            #         f"{self._base_url}/weather/{city}",
            #         headers={"Authorization": f"Bearer {self._api_key}"},
            #     )
            #     return response.json()

            # Simulated response
            await asyncio.sleep(0.2)  # Simulate API latency
            weather_data = {
                "Paris": {"temperature": 18, "humidity": 65, "conditions": "Partly cloudy"},
                "Tokyo": {"temperature": 22, "humidity": 70, "conditions": "Sunny"},
                "New York": {"temperature": 15, "humidity": 55, "conditions": "Cloudy"},
            }
            return weather_data.get(city, {"temperature": 20, "humidity": 60, "conditions": "Unknown"})

        async def fetch_exchange_rate(
            self, from_currency: str, to_currency: str
        ) -> float:
            """Fetch exchange rate (simulated)."""
            # In production:
            # async with httpx.AsyncClient() as client:
            #     response = await client.get(
            #         f"{self._base_url}/exchange",
            #         params={"from": from_currency, "to": to_currency},
            #         headers={"Authorization": f"Bearer {self._api_key}"},
            #     )
            #     data = response.json()
            #     return data["rate"]

            # Simulated rates
            await asyncio.sleep(0.1)
            rates = {
                ("USD", "EUR"): 0.92,
                ("USD", "GBP"): 0.79,
                ("EUR", "USD"): 1.09,
            }
            return rates.get((from_currency, to_currency), 1.0)

    # USER CODE (untrusted - runs in WASM sandbox)
    @app.step
    async def analyze_travel_cost(city: str, budget_usd: float, services=None):
        """
        User-provided travel analysis.
        Can call APIs via service but NO direct network access.
        """
        # Fetch data via services (execute on trusted workers)
        weather = await services["ExternalAPIService"].fetch_weather(city)
        exchange_rate = await services["ExternalAPIService"].fetch_exchange_rate(
            "USD", "EUR"
        )
        # Process in sandbox
        budget_eur = budget_usd * exchange_rate
        temp = weather.get("temperature", 20)
        # User's logic
        if temp < 10:
            recommendation = "Too cold - bring warm clothes!"
        elif temp > 30:
            recommendation = "Too hot - consider air conditioning!"
        else:
            recommendation = "Perfect weather - Go!"

        return {
            "city": city,
            "temperature": temp,
            "conditions": weather.get("conditions", "Unknown"),
            "budget_usd": budget_usd,
            "budget_eur": round(budget_eur, 2),
            "recommendation": recommendation,
        }

    # YOUR CODE (trusted - orchestrates)
    @app.workflow
    async def plan_trip(city: str, budget_usd: float, services=None):
        """Run user's travel analysis safely."""
        return await analyze_travel_cost(city, budget_usd, services=services)

    await app.publish()

    # Execute the workflow for multiple destinations
    destinations = [
        ("Paris", 2000),
        ("Tokyo", 3000),
        ("New York", 1500),
    ]

    for city, budget in destinations:
        print(f"\nAnalyzing trip to {city} with ${budget} budget...")
        result = await app.plan_trip(city=city, budget_usd=budget).wait_result()
        print(f"  Weather: {result['temperature']}C, {result['conditions']}")
        print(f"  Budget: ${result['budget_usd']} USD = {result['budget_eur']} EUR")
        print(f"  Recommendation: {result['recommendation']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
