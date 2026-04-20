import asyncio
import time
from dataclasses import dataclass
from typing import Optional
from blazing import Blazing
from blazing.base import BaseService


# =============================================================================
# Simulated Market Data API
# =============================================================================

class SimulatedMarketAPI:
    """Simulates an external market data API with rate limiting."""

    def __init__(self, rate_limit: int = 10, window_seconds: float = 1.0):
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self.call_times: list[float] = []
        self.total_calls = 0

    async def _throttle(self):
        """Apply rate limiting."""
        now = time.time()
        self.call_times = [t for t in self.call_times if now - t < self.window_seconds]

        if len(self.call_times) >= self.rate_limit:
            wait_time = self.window_seconds - (now - self.call_times[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        self.call_times.append(time.time())
        self.total_calls += 1

    async def get_stock_price(self, symbol: str) -> Optional[dict]:
        """Fetch stock price (simulated with throttling)."""
        await self._throttle()

        # Simulate some failures
        if symbol == "INVALID":
            return None

        # Simulated prices
        prices = {
            "AAPL": 150.25, "GOOGL": 141.80, "MSFT": 378.50, "AMZN": 178.25,
            "META": 505.75, "NVDA": 875.50, "TSLA": 248.50, "JPM": 198.25,
            "V": 275.50, "JNJ": 155.75, "WMT": 165.25, "PG": 158.50,
        }

        price = prices.get(symbol, 100.0 + hash(symbol) % 100)
        return {"symbol": symbol, "price": price, "timestamp": time.time()}


# =============================================================================
# Stock Data Service
# =============================================================================

class StockDataService(BaseService):
    """
    Service for fetching and processing stock data.

    Follows the tradegrid pattern:
    - __init__ receives connector_instances dict
    - Methods use self.connector_instances['API'].method()
    """

    def __init__(self, connectors):
        self.connectors = connectors
        self.api = connectors.get('market_api', SimulatedMarketAPI())

    async def fetch_stock_price(self, symbol: str) -> Optional[dict]:
        """Fetch price for a single stock."""
        return await self.api.get_stock_price(symbol)

    async def process_batch(self, symbols: list[str]) -> dict:
        """
        Process a batch of stocks, collecting results and errors.

        Pattern from tradegrid:
            for stock_id in batch_stock_ids:
                ts_data = await services["TradeGrid"]._add_stock_price(stock_id)
                if ts_data is not None:
                    time_series_to_add.extend(ts_data)
        """
        results = []
        errors = []

        for symbol in symbols:
            try:
                data = await self.fetch_stock_price(symbol)
                if data:
                    results.append(data)
                else:
                    errors.append({"symbol": symbol, "error": "Not found"})
            except Exception as e:
                errors.append({"symbol": symbol, "error": str(e)})

        return {
            "results": results,
            "errors": errors,
            "success_count": len(results),
            "error_count": len(errors)
        }


# =============================================================================
# Batch Processing Workflow
# =============================================================================

async def process_stock_batch_workflow(
    symbols: list[str],
    batch_size: int = 5,
    services: dict = None
) -> dict:
    """
    Workflow that processes stocks in batches.

    Args:
        symbols: List of stock symbols to process
        batch_size: Number of stocks per batch
        services: Injected services dict

    Returns:
        Summary of processing results
    """
    service = services['StockDataService'] if services else StockDataService({})

    all_results = []
    all_errors = []
    batches_processed = 0

    # Process in batches
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        print(f"  Processing batch {batch_num}/{total_batches}: {batch}")

        batch_result = await service.process_batch(batch)

        all_results.extend(batch_result["results"])
        all_errors.extend(batch_result["errors"])
        batches_processed += 1

    return {
        "total_symbols": len(symbols),
        "success_count": len(all_results),
        "error_count": len(all_errors),
        "batches_processed": batches_processed,
        "results": all_results,
        "errors": all_errors
    }


# =============================================================================
# Throttling Configuration Examples
# =============================================================================

@dataclass
class ThrottleConfig:
    """Throttling configuration (from tradegrid patterns)."""
    limit: int          # Max requests
    window: float       # Time window in seconds
    mode: str           # 'fixed' or 'rolling'


# Common API throttling configurations
THROTTLE_CONFIGS = {
    # Conservative: 10 requests per second
    "conservative": ThrottleConfig(limit=10, window=1.0, mode="fixed"),

    # Standard: 100 requests per minute
    "standard": ThrottleConfig(limit=100, window=60.0, mode="rolling"),

    # Aggressive: 1000 requests per minute (paid tier)
    "aggressive": ThrottleConfig(limit=1000, window=60.0, mode="rolling"),
}


# =============================================================================
# Main Demo
# =============================================================================

async def main():
    """Demonstrate batch stock processing with throttling."""
    print("=" * 60)
    print("Batch Stock Processing Demo")
    print("=" * 60)

    # Sample stock symbols
    symbols = [
        "AAPL", "GOOGL", "MSFT", "AMZN", "META",
        "NVDA", "TSLA", "JPM", "V", "JNJ",
        "WMT", "PG", "INVALID",  # Include one that will fail
    ]

    # Create service with simulated API (rate limited)
    api = SimulatedMarketAPI(rate_limit=5, window_seconds=0.5)
    service = StockDataService({"market_api": api})
    services = {"StockDataService": service}

    print(f"\nProcessing {len(symbols)} stocks with rate limit: 5 req/0.5s")
    print("-" * 60)

    start_time = time.time()

    result = await process_stock_batch_workflow(
        symbols=symbols,
        batch_size=4,
        services=services
    )

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)
    print(f"Total symbols:     {result['total_symbols']}")
    print(f"Successful:        {result['success_count']}")
    print(f"Failed:            {result['error_count']}")
    print(f"Batches processed: {result['batches_processed']}")
    print(f"Total API calls:   {api.total_calls}")
    print(f"Elapsed time:      {elapsed:.2f}s")

    if result['errors']:
        print(f"\nErrors:")
        for error in result['errors']:
            print(f"  - {error['symbol']}: {error['error']}")

    print("\n" + "=" * 60)
    print("Throttling Configurations Available:")
    print("=" * 60)
    for name, config in THROTTLE_CONFIGS.items():
        print(f"  {name:12}: {config.limit} req / {config.window}s ({config.mode})")


if __name__ == "__main__":
    asyncio.run(main())
