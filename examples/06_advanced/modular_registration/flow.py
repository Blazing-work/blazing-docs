import asyncio
from blazing import Blazing
from blazing.base import BaseService


# =============================================================================
# Trading Module
# =============================================================================

def register_trading_module(app: Blazing) -> dict:
    """
    Register trading domain steps and workflows.

    Returns manifest of registered components.
    """
    manifest = {"services": [], "steps": [], "workflows": []}

    @app.service
    class TradingService(BaseService):
        """Service for trade execution and management."""

        def __init__(self, connectors):
            self.connectors = connectors
            self.executed_trades = []

        async def execute_trade(self, symbol: str, quantity: int, side: str) -> dict:
            """Execute a trade order."""
            trade = {
                "symbol": symbol,
                "quantity": quantity,
                "side": side,
                "status": "executed",
                "trade_id": f"TRD-{len(self.executed_trades) + 1:05d}"
            }
            self.executed_trades.append(trade)
            return trade

        async def get_position(self, symbol: str) -> dict:
            """Get current position for a symbol."""
            qty = sum(
                t["quantity"] if t["side"] == "BUY" else -t["quantity"]
                for t in self.executed_trades
                if t["symbol"] == symbol
            )
            return {"symbol": symbol, "quantity": qty}

    manifest["services"].append("TradingService")

    @app.step
    async def validate_order(symbol: str, quantity: int, services=None) -> dict:
        """Validate a trade order before execution."""
        errors = []
        if not symbol or len(symbol) > 5:
            errors.append("Invalid symbol")
        if quantity <= 0:
            errors.append("Quantity must be positive")
        return {"valid": len(errors) == 0, "errors": errors}

    manifest["steps"].append("validate_order")

    @app.step
    async def execute_order(symbol: str, quantity: int, side: str, services=None) -> dict:
        """Execute a validated order."""
        if services:
            return await services["TradingService"].execute_trade(symbol, quantity, side)
        return {"symbol": symbol, "quantity": quantity, "side": side, "status": "simulated"}

    manifest["steps"].append("execute_order")

    @app.workflow
    async def trading_workflow(symbol: str, quantity: int, side: str, services=None) -> dict:
        """
        Complete trading workflow: validate and execute.

        Pattern from production:
            @app.route
            async def execute_trade_route(order_params, services=None):
                validation = await validate_order(order_params, services=services)
                if validation['valid']:
                    return await execute_order(order_params, services=services)
        """
        validation = await validate_order(symbol, quantity, services=services)
        if not validation["valid"]:
            return {"success": False, "errors": validation["errors"]}

        result = await execute_order(symbol, quantity, side, services=services)
        return {"success": True, "trade": result}

    manifest["workflows"].append("trading_workflow")

    return manifest


# =============================================================================
# Analytics Module
# =============================================================================

def register_analytics_module(app: Blazing) -> dict:
    """
    Register analytics domain steps and workflows.

    Returns manifest of registered components.
    """
    manifest = {"services": [], "steps": [], "workflows": []}

    @app.service
    class AnalyticsService(BaseService):
        """Service for financial analytics calculations."""

        def __init__(self, connectors):
            self.connectors = connectors

        async def calculate_metrics(self, symbol: str) -> dict:
            """Calculate key metrics for a symbol."""
            # Simulated metrics
            return {
                "symbol": symbol,
                "pe_ratio": 15.5,
                "eps": 5.25,
                "market_cap": "2.5T",
                "dividend_yield": 0.5
            }

        async def calculate_risk(self, portfolio: list) -> dict:
            """Calculate portfolio risk metrics."""
            return {
                "var_95": 0.025,
                "sharpe_ratio": 1.5,
                "beta": 1.1,
                "positions": len(portfolio)
            }

    manifest["services"].append("AnalyticsService")

    @app.step
    async def fetch_metrics(symbol: str, services=None) -> dict:
        """Fetch metrics for a symbol."""
        if services:
            return await services["AnalyticsService"].calculate_metrics(symbol)
        return {"symbol": symbol, "pe_ratio": 15.0}

    manifest["steps"].append("fetch_metrics")

    @app.step
    async def calculate_portfolio_risk(symbols: list, services=None) -> dict:
        """Calculate risk for a portfolio."""
        if services:
            return await services["AnalyticsService"].calculate_risk(symbols)
        return {"var_95": 0.02, "positions": len(symbols)}

    manifest["steps"].append("calculate_portfolio_risk")

    @app.workflow
    async def analytics_workflow(symbols: list, services=None) -> dict:
        """
        Run analytics on a list of symbols.
        """
        metrics = []
        for symbol in symbols:
            m = await fetch_metrics(symbol, services=services)
            metrics.append(m)

        risk = await calculate_portfolio_risk(symbols, services=services)

        return {
            "metrics": metrics,
            "risk": risk,
            "symbols_analyzed": len(symbols)
        }

    manifest["workflows"].append("analytics_workflow")

    return manifest


# =============================================================================
# Reporting Module
# =============================================================================

def register_reporting_module(app: Blazing) -> dict:
    """
    Register reporting domain steps and workflows.

    Returns manifest of registered components.
    """
    manifest = {"services": [], "steps": [], "workflows": []}

    @app.step
    async def generate_summary(data: dict, services=None) -> str:
        """Generate a text summary from data."""
        lines = ["=== Report Summary ==="]
        for key, value in data.items():
            lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    manifest["steps"].append("generate_summary")

    @app.step
    async def format_report(summary: str, format_type: str = "text", services=None) -> dict:
        """Format report in specified format."""
        return {
            "format": format_type,
            "content": summary,
            "generated": True
        }

    manifest["steps"].append("format_report")

    @app.workflow
    async def reporting_workflow(data: dict, format_type: str = "text", services=None) -> dict:
        """
        Generate and format a report.
        """
        summary = await generate_summary(data, services=services)
        report = await format_report(summary, format_type, services=services)
        return report

    manifest["workflows"].append("reporting_workflow")

    return manifest


# =============================================================================
# Conditional Module Registration
# =============================================================================

def register_with_features(app: Blazing, features: dict) -> dict:
    """
    Register modules conditionally based on feature flags.

    Usage:
        register_with_features(app, {
            "trading_enabled": True,
            "analytics_enabled": True,
            "reporting_enabled": False,
        })
    """
    manifest = {"trading": None, "analytics": None, "reporting": None}

    if features.get("trading_enabled", False):
        manifest["trading"] = register_trading_module(app)
        print("  [Module] Trading: Registered")

    if features.get("analytics_enabled", False):
        manifest["analytics"] = register_analytics_module(app)
        print("  [Module] Analytics: Registered")

    if features.get("reporting_enabled", False):
        manifest["reporting"] = register_reporting_module(app)
        print("  [Module] Reporting: Registered")

    return manifest


# =============================================================================
# Main Demo
# =============================================================================

async def main():
    """Demonstrate modular registration pattern."""
    print("=" * 60)
    print("Modular Registration Pattern Demo")
    print("=" * 60)

    # Create Blazing app
    app = Blazing(api_url="http://localhost:8000", api_token="demo-token")

    # Method 1: Register modules individually
    print("\n1. Individual Module Registration")
    print("-" * 40)

    trading_manifest = register_trading_module(app)
    print(f"  Trading Module:")
    print(f"    Services:  {trading_manifest['services']}")
    print(f"    Steps:     {trading_manifest['steps']}")
    print(f"    Workflows: {trading_manifest['workflows']}")

    analytics_manifest = register_analytics_module(app)
    print(f"  Analytics Module:")
    print(f"    Services:  {analytics_manifest['services']}")
    print(f"    Steps:     {analytics_manifest['steps']}")
    print(f"    Workflows: {analytics_manifest['workflows']}")

    reporting_manifest = register_reporting_module(app)
    print(f"  Reporting Module:")
    print(f"    Steps:     {reporting_manifest['steps']}")
    print(f"    Workflows: {reporting_manifest['workflows']}")

    # Verify registration
    print("\n2. Verify Registration")
    print("-" * 40)
    print(f"  Total services registered: {len(app._service_registry)}")
    print(f"  Total steps registered:    {len(app._step_funcs)}")
    print(f"  Total workflows registered: {len(app._route_funcs)}")

    # Method 2: Feature-based registration (new app)
    print("\n3. Feature-Based Registration")
    print("-" * 40)

    app2 = Blazing(api_url="http://localhost:8000", api_token="demo-token")

    features = {
        "trading_enabled": True,
        "analytics_enabled": True,
        "reporting_enabled": False,  # Disabled
    }

    manifest = register_with_features(app2, features)
    print(f"\n  Enabled modules: {[k for k, v in manifest.items() if v]}")
    print(f"  Disabled modules: {[k for k, v in manifest.items() if not v]}")

    # Summary
    print("\n" + "=" * 60)
    print("Modular Architecture Benefits:")
    print("=" * 60)
    print("  1. Separation of Concerns - Each domain is isolated")
    print("  2. Testability - Test modules independently")
    print("  3. Scalability - Add new modules without changing existing")
    print("  4. Feature Flags - Enable/disable features dynamically")
    print("  5. Manifest - Track what's registered for documentation")


if __name__ == "__main__":
    asyncio.run(main())
