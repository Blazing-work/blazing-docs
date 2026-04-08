import asyncio
from blazing import Blazing, run_sandboxed, create_signing_key
from blazing.base import BaseService


# =============================================================================
#
#                         YOUR SIDE (Platform Owner)
#
# =============================================================================


async def setup_platform():
    """
    YOUR SETUP CODE - Run this to initialize your trading platform.

    This sets up:
    1. MarketDataService - data your users can access
    2. @app.workflow with run_sandboxed() - secure user code execution
    3. app.publish() - registers everything with Blazing
    """
    print("=" * 60)
    print("PLATFORM SETUP (Your Side)")
    print("=" * 60)

    # Initialize Blazing with your API credentials
    app = Blazing(
        api_url="http://localhost:8000",
        api_token="your-platform-token"
    )

    # Generate signing key ONCE (store this securely - env var, secrets manager)
    signing_key = create_signing_key()

    # -------------------------------------------------------------------------
    # Step 1: Define Services Your Users Can Access
    # -------------------------------------------------------------------------

    @app.service
    class MarketDataService(BaseService):
        """
        Platform service that provides market data to your users' strategies.

        This runs on YOUR trusted workers with real database/API access.
        Your users' sandboxed code can only call methods you expose here.
        """

        def __init__(self, connectors):
            # In production: self._db = connectors.get('market_db')
            pass

        def get_historical_prices(self, symbol: str, days: int = 30) -> list:
            """Fetch historical OHLCV price data for a symbol."""
            import random
            random.seed(hash(symbol) % 1000)

            base_price = {"AAPL": 150.0, "GOOGL": 140.0, "TSLA": 250.0, "BTC": 45000.0}.get(symbol, 100.0)
            prices = []

            for i in range(days):
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

        def get_current_price(self, symbol: str) -> float:
            """Get the current price for a symbol."""
            import random
            random.seed(hash(symbol + "current") % 1000)
            base = {"AAPL": 150.0, "GOOGL": 140.0, "TSLA": 250.0, "BTC": 45000.0}.get(symbol, 100.0)
            return round(base + random.uniform(-10, 10), 2)

        def calculate_sma(self, prices: list, period: int = 20) -> float:
            """Calculate Simple Moving Average."""
            closes = [p['close'] for p in prices[-period:]]
            return round(sum(closes) / len(closes), 2) if closes else 0

        def calculate_rsi(self, prices: list, period: int = 14) -> float:
            """Calculate Relative Strength Index."""
            closes = [p['close'] for p in prices]
            gains, losses = [], []
            for i in range(1, len(closes)):
                change = closes[i] - closes[i-1]
                gains.append(max(change, 0))
                losses.append(abs(min(change, 0)))

            avg_gain = sum(gains[-period:]) / period if len(gains) >= period else 0
            avg_loss = sum(losses[-period:]) / period if len(losses) >= period else 0.001
            rs = avg_gain / avg_loss
            return round(100 - (100 / (1 + rs)), 2)

    print("1. Registered MarketDataService")

    # -------------------------------------------------------------------------
    # Step 2: Define Workflow That Executes User Code Securely
    # -------------------------------------------------------------------------

    @app.workflow
    async def run_user_strategy(
        user_code: str,
        symbol: str,
        services=None
    ) -> dict:
        """
        Workflow that runs a user-submitted trading strategy.

        This is WHERE USER CODE RUNS - securely sandboxed via run_sandboxed().

        Args:
            user_code: Python source code of the strategy (string)
            symbol: Stock/crypto symbol to analyze
            services: Injected services dict

        Returns:
            Strategy decision with metadata
        """
        # =====================================================================
        #     THIS IS WHERE USER CODE RUNS (sandboxed, limited access)
        #
        #     run_sandboxed() handles ALL security automatically:
        #     - AST validation
        #     - Code signing
        #     - Signature verification
        #     - Bytecode validation
        #     - Pyodide WASM sandbox
        # =====================================================================

        result = await run_sandboxed(
            user_code,
            symbol,                                        # Passed as first arg to user function
            signing_key=signing_key,                       # Your platform's signing key
            func_name='strategy',                          # Function to call in user code
            services={'MarketData': services['MarketDataService']}  # Services exposed to user
        )

        # Add metadata (this runs in YOUR trusted code, after sandbox)
        import time
        result['symbol'] = symbol
        result['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
        result['executed_in'] = 'pyodide_sandbox'

        return result

    print("2. Registered run_user_strategy workflow (uses run_sandboxed)")

    # -------------------------------------------------------------------------
    # Step 3: Publish to Blazing Backend
    # -------------------------------------------------------------------------

    await app.publish()
    print("3. Published to Blazing backend")

    print(f"4. Signing key ready: {signing_key[:8].hex()}...")
    print("   (Store this securely - env var, secrets manager)")

    print("\nPlatform ready! Your users can now submit strategies.")
    return app, signing_key


# =============================================================================
#
#                    YOUR USER'S SIDE (End Users)
#
# =============================================================================

# Example strategy code that your users would write and submit.
# This is a STRING - exactly what your user would type in a web form.

USER_SMA_STRATEGY = '''
def strategy(symbol: str, services: dict) -> dict:
    """
    SMA crossover strategy.
    BUY when price > SMA(20), SELL when price < SMA(20).
    """
    market = services['MarketData']

    prices = market.get_historical_prices(symbol, days=30)
    current_price = market.get_current_price(symbol)
    sma_20 = market.calculate_sma(prices, period=20)

    if current_price > sma_20:
        return {
            'action': 'BUY',
            'confidence': 0.7,
            'reason': f'Price ${current_price} above SMA(20) ${sma_20}'
        }
    elif current_price < sma_20:
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': f'Price ${current_price} below SMA(20) ${sma_20}'
        }
    return {
        'action': 'HOLD',
        'confidence': 0.5,
        'reason': f'Price ${current_price} near SMA(20) ${sma_20}'
    }
'''

USER_RSI_STRATEGY = '''
def strategy(symbol: str, services: dict) -> dict:
    """
    RSI mean reversion strategy.
    BUY when RSI < 30 (oversold), SELL when RSI > 70 (overbought).
    """
    market = services['MarketData']

    prices = market.get_historical_prices(symbol, days=30)
    rsi = market.calculate_rsi(prices, period=14)

    if rsi < 30:
        return {
            'action': 'BUY',
            'confidence': min((30 - rsi) / 30, 0.95),
            'reason': f'RSI {rsi} indicates oversold'
        }
    elif rsi > 70:
        return {
            'action': 'SELL',
            'confidence': min((rsi - 70) / 30, 0.95),
            'reason': f'RSI {rsi} indicates overbought'
        }
    return {
        'action': 'HOLD',
        'confidence': 0.6,
        'reason': f'RSI {rsi} in neutral zone'
    }
'''


async def user_submits_strategy(
    app: Blazing,
    user_code: str,
    symbol: str
):
    """
    YOUR USER'S CODE - How they submit a strategy for execution.

    This is what happens when a user clicks "Run Strategy" on your platform.
    Note: NO signing required on user side - run_sandboxed() handles it!
    """
    print(f"\nSubmitting strategy for {symbol}")
    print("-" * 40)

    try:
        # Simply call the workflow with the code string
        # Security is handled by run_sandboxed() inside the workflow
        result = await app.run_user_strategy(
            user_code=user_code,
            symbol=symbol
        ).wait_result()

        print(f"  Symbol:     {result.get('symbol')}")
        print(f"  Action:     {result.get('action')}")
        print(f"  Confidence: {result.get('confidence', 0):.0%}")
        print(f"  Reason:     {result.get('reason')}")
        print(f"  Executed:   {result.get('executed_in')}")
        return result

    except Exception as e:
        print(f"  Error: {e}")
        return None


# =============================================================================
#
#                              DEMO
#
# =============================================================================

async def main():
    """
    Demo showing both sides of the platform.
    """
    # =========================================================================
    # YOUR SIDE: Set up the platform
    # =========================================================================
    app, signing_key = await setup_platform()

    # =========================================================================
    # YOUR USER'S SIDE: Submit strategies
    # =========================================================================
    print("\n" + "=" * 60)
    print("USER SUBMISSIONS (Your User's Side)")
    print("=" * 60)

    # User 1 submits SMA strategy for AAPL
    await user_submits_strategy(app, USER_SMA_STRATEGY, symbol="AAPL")

    # User 2 submits RSI strategy for TSLA
    await user_submits_strategy(app, USER_RSI_STRATEGY, symbol="TSLA")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 60)
    print("ARCHITECTURE SUMMARY")
    print("=" * 60)
    print("""
    YOUR SIDE (Platform Owner):
    ---------------------------
    1. @app.service - MarketDataService (trusted, real DB access)
    2. @app.workflow - uses run_sandboxed() for secure execution
    3. await app.publish()
    4. signing_key = create_signing_key()

    YOUR USER'S SIDE (End Users):
    -----------------------------
    1. Write strategy as Python code string
    2. Submit to run_user_strategy workflow
    3. Get result back

    SECURITY (ALL handled by run_sandboxed()):
    ------------------------------------------
    Layer 1: AST validation (blocks eval, exec, __import__)
    Layer 2: Cryptographic signing (HMAC-SHA256)
    Layer 3: Signature verification
    Layer 4: Bytecode validation (blocks dangerous opcodes)
    Layer 5: Pyodide WASM sandbox (no I/O access)

    KEY BENEFIT: You can't mess up security - run_sandboxed() handles it!
    """)


if __name__ == "__main__":
    asyncio.run(main())
