"""
Example: Dynamic Trading Strategy Execution

This example demonstrates how users can submit custom trading strategies as
serialized Python code to be executed safely in a sandboxed environment.

Use Case: SaaS Platform for Algorithmic Trading
- Platform users define their own trading strategies
- Strategies are submitted as Python code
- Platform executes strategies in isolated sandboxes
- Each user's code is protected from others
- Platform infrastructure is protected from user code

Security Model:
1. User code runs in Pyodide WASM sandbox (no I/O)
2. Strategies can only access provided market data
3. Strategies cannot import unauthorized modules
4. Platform controls what services/connectors are available
5. Resource limits prevent DoS

Usage:
    uv run python docs/examples/dynamic_trading_strategies.py
"""

import asyncio
import base64
import dill
from blazing import Blazing
from blazing.base import BaseService


# =============================================================================
# Define a Market Data Service (platform-provided, trusted)
# =============================================================================
class MarketDataService(BaseService):
    """
    Platform-provided service that gives strategies access to market data.
    This runs on TRUSTED workers with real database/API access.
    """

    def __init__(self, connectors):
        self._db = connectors.get('db')  # Platform's database connection

    async def get_historical_prices(self, symbol: str, days: int = 30) -> list:
        """
        Fetch historical price data for a symbol.
        In production, this would query a real database.
        """
        # Mock data for example
        import random
        base_price = 100.0
        prices = []
        for i in range(days):
            # Simulate price movement
            change = random.uniform(-2.0, 2.0)
            base_price += change
            prices.append({
                'day': i,
                'open': round(base_price - random.uniform(0, 1), 2),
                'high': round(base_price + random.uniform(0, 2), 2),
                'low': round(base_price - random.uniform(0, 2), 2),
                'close': round(base_price, 2),
                'volume': random.randint(1000000, 5000000)
            })
        return prices

    async def get_current_price(self, symbol: str) -> float:
        """Get the current price for a symbol."""
        # Mock current price
        import random
        return round(100.0 + random.uniform(-10, 10), 2)

    async def calculate_indicators(self, prices: list, indicators: list) -> dict:
        """
        Calculate technical indicators (SMA, RSI, etc.)
        In production, this might call a specialized analytics service.
        """
        results = {}

        if 'sma_20' in indicators:
            # Simple Moving Average (20 days)
            closes = [p['close'] for p in prices[-20:]]
            results['sma_20'] = sum(closes) / len(closes)

        if 'rsi' in indicators:
            # Simplified RSI calculation
            closes = [p['close'] for p in prices]
            gains = []
            losses = []
            for i in range(1, len(closes)):
                change = closes[i] - closes[i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))

            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
            rs = avg_gain / avg_loss if avg_loss != 0 else 0
            results['rsi'] = 100 - (100 / (1 + rs))

        return results


async def main():
    # Initialize Blazing with API backend
    app = Blazing(
        api_url="http://localhost:8000",
        api_token="test-token"
    )

    # Register the market data service
    app.service(MarketDataService)

    # =========================================================================
    # Define sandboxed strategy executor step
    # =========================================================================
    @app.step
    async def execute_strategy(
        serialized_strategy: str,
        symbol: str,
        services=None
    ):
        """
        Execute a user-defined trading strategy in Pyodide sandbox.

        The strategy function receives:
        - symbol: Stock/crypto symbol
        - services: Access to MarketDataService methods

        Returns:
            Strategy decision: {'action': 'BUY'|'SELL'|'HOLD', 'confidence': float, 'reason': str}
        """
        import base64
        import dill

        # Deserialize the user's strategy function
        strategy_bytes = base64.b64decode(serialized_strategy)
        user_strategy = dill.loads(strategy_bytes)

        # Execute the strategy with access to services
        result = await user_strategy(symbol, services=services)

        return result

    # =========================================================================
    # Define orchestration workflow
    # =========================================================================
    @app.workflow
    async def run_strategy_analysis(
        symbol: str,
        strategy_code: str,
        services=None
    ):
        """
        Run a user-submitted strategy and return the decision.

        Args:
            symbol: Stock/crypto symbol to analyze
            strategy_code: Base64-encoded dill-serialized strategy function

        Returns:
            Strategy decision with metadata
        """
        # Execute the strategy
        decision = await execute_strategy(strategy_code, symbol)

        # Add metadata
        decision['symbol'] = symbol
        decision['timestamp'] = 'mock-timestamp'

        return decision

    # Publish
    await app.publish()
    print("✓ Trading platform published\n")

    # =========================================================================
    # Example User Strategy 1: Simple Moving Average Crossover
    # =========================================================================
    async def sma_crossover_strategy(symbol: str, services=None):
        """
        Classic SMA crossover strategy:
        - BUY when price > SMA(20)
        - SELL when price < SMA(20)
        """
        # Get historical prices using platform service
        prices = await services['MarketDataService'].get_historical_prices(symbol, days=30)
        current_price = await services['MarketDataService'].get_current_price(symbol)

        # Calculate SMA(20)
        indicators = await services['MarketDataService'].calculate_indicators(
            prices,
            indicators=['sma_20']
        )
        sma_20 = indicators['sma_20']

        # Make decision
        if current_price > sma_20:
            return {
                'action': 'BUY',
                'confidence': 0.7,
                'reason': f'Price ${current_price} above SMA(20) ${sma_20:.2f}'
            }
        elif current_price < sma_20:
            return {
                'action': 'SELL',
                'confidence': 0.7,
                'reason': f'Price ${current_price} below SMA(20) ${sma_20:.2f}'
            }
        else:
            return {
                'action': 'HOLD',
                'confidence': 0.5,
                'reason': 'Price at SMA(20), waiting for clear signal'
            }

    # Serialize and execute
    strategy1_code = base64.b64encode(dill.dumps(sma_crossover_strategy)).decode('utf-8')
    unit1 = await app.run(
        "run_strategy_analysis",
        symbol="AAPL",
        strategy_code=strategy1_code
    )
    result1 = await unit1.result()
    print("Strategy 1 - SMA Crossover:")
    print(f"  Action: {result1['action']}")
    print(f"  Confidence: {result1['confidence']}")
    print(f"  Reason: {result1['reason']}\n")

    # =========================================================================
    # Example User Strategy 2: RSI-based Mean Reversion
    # =========================================================================
    async def rsi_mean_reversion_strategy(symbol: str, services=None):
        """
        RSI mean reversion strategy:
        - BUY when RSI < 30 (oversold)
        - SELL when RSI > 70 (overbought)
        - HOLD otherwise
        """
        # Get data
        prices = await services['MarketDataService'].get_historical_prices(symbol, days=30)

        # Calculate RSI
        indicators = await services['MarketDataService'].calculate_indicators(
            prices,
            indicators=['rsi']
        )
        rsi = indicators['rsi']

        # Make decision based on RSI
        if rsi < 30:
            return {
                'action': 'BUY',
                'confidence': min((30 - rsi) / 30, 0.95),
                'reason': f'RSI {rsi:.1f} indicates oversold conditions'
            }
        elif rsi > 70:
            return {
                'action': 'SELL',
                'confidence': min((rsi - 70) / 30, 0.95),
                'reason': f'RSI {rsi:.1f} indicates overbought conditions'
            }
        else:
            return {
                'action': 'HOLD',
                'confidence': 0.6,
                'reason': f'RSI {rsi:.1f} in neutral zone (30-70)'
            }

    strategy2_code = base64.b64encode(dill.dumps(rsi_mean_reversion_strategy)).decode('utf-8')
    unit2 = await app.run(
        "run_strategy_analysis",
        symbol="TSLA",
        strategy_code=strategy2_code
    )
    result2 = await unit2.result()
    print("Strategy 2 - RSI Mean Reversion:")
    print(f"  Action: {result2['action']}")
    print(f"  Confidence: {result2['confidence']}")
    print(f"  Reason: {result2['reason']}\n")

    # =========================================================================
    # Example User Strategy 3: Multi-signal combination
    # =========================================================================
    async def combined_strategy(symbol: str, services=None):
        """
        Combine multiple signals for higher confidence.
        Uses both SMA and RSI.
        """
        # Get all required data
        prices = await services['MarketDataService'].get_historical_prices(symbol, days=30)
        current_price = await services['MarketDataService'].get_current_price(symbol)
        indicators = await services['MarketDataService'].calculate_indicators(
            prices,
            indicators=['sma_20', 'rsi']
        )

        sma_20 = indicators['sma_20']
        rsi = indicators['rsi']

        # Scoring system
        buy_score = 0
        sell_score = 0
        reasons = []

        # SMA signal
        if current_price > sma_20:
            buy_score += 1
            reasons.append(f"Price above SMA ({current_price:.2f} > {sma_20:.2f})")
        else:
            sell_score += 1
            reasons.append(f"Price below SMA ({current_price:.2f} < {sma_20:.2f})")

        # RSI signal
        if rsi < 30:
            buy_score += 1
            reasons.append(f"RSI oversold ({rsi:.1f})")
        elif rsi > 70:
            sell_score += 1
            reasons.append(f"RSI overbought ({rsi:.1f})")

        # Make decision
        if buy_score > sell_score:
            return {
                'action': 'BUY',
                'confidence': buy_score / 2,
                'reason': '; '.join(reasons)
            }
        elif sell_score > buy_score:
            return {
                'action': 'SELL',
                'confidence': sell_score / 2,
                'reason': '; '.join(reasons)
            }
        else:
            return {
                'action': 'HOLD',
                'confidence': 0.5,
                'reason': 'Mixed signals: ' + '; '.join(reasons)
            }

    strategy3_code = base64.b64encode(dill.dumps(combined_strategy)).decode('utf-8')
    unit3 = await app.run(
        "run_strategy_analysis",
        symbol="BTC",
        strategy_code=strategy3_code
    )
    result3 = await unit3.result()
    print("Strategy 3 - Combined Signals:")
    print(f"  Action: {result3['action']}")
    print(f"  Confidence: {result3['confidence']}")
    print(f"  Reason: {result3['reason']}\n")

    print("✓ All trading strategies executed successfully!\n")
    print("Security Benefits:")
    print("- User strategies run in Pyodide WASM sandbox")
    print("- No direct database/network access from user code")
    print("- Can only access platform-provided services")
    print("- Each user's code is isolated from others")
    print("- Platform infrastructure is protected")
    print("\nBusiness Value:")
    print("- Users can write custom strategies without platform code changes")
    print("- Platform maintains control over data access")
    print("- Easy to add new features via services")
    print("- Scalable multi-tenant architecture")


if __name__ == "__main__":
    asyncio.run(main())
