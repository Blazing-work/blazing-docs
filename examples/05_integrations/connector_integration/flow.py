import asyncio
from dataclasses import dataclass
from typing import Optional, Any
from blazing.base import BaseService


# =============================================================================
# Connector Configurations (production patterns)
# =============================================================================

@dataclass
class RESTConnectorConfig:
    """
    REST API connector configuration.

    Based on production patterns:
        connector_config = {
            'name': 'GuruFocus',
            'target_class_name': 'RESTConnector',
            'auth': {"token": "api-key"},
            'pool': {"pool_maxsize": 20, "timeout": 600},
            'throttling': {'limit': 10, 'window': 1, 'mode': 'fixed'},
        }
    """
    name: str
    base_url: str
    auth: dict = None
    pool_maxsize: int = 20
    timeout: int = 600
    throttle_limit: int = 100
    throttle_window: int = 60
    throttle_mode: str = "rolling"  # 'fixed' or 'rolling'


@dataclass
class SQLConnectorConfig:
    """
    SQL database connector configuration.

    Based on production patterns:
        connector_config = {
            'name': 'PostgreSQL',
            'target_class_name': 'SQLAlchemyConnector',
            'auth': {"address": "localhost:5432", "dbname": "db", ...},
        }
    """
    name: str
    address: str
    dbname: str
    user: str
    password: str
    pool_size: int = 5


# =============================================================================
# Simulated Connectors
# =============================================================================

class SimulatedRESTConnector:
    """
    Simulated REST connector for demonstration.

    In production, use blazing.RESTConnector which provides:
    - Connection pooling with httpx
    - Automatic retry with backoff
    - Rate limiting
    - Auth token refresh
    """

    def __init__(self, config: RESTConnectorConfig):
        self.config = config
        self.name = config.name
        self._connected = False

    async def connect(self):
        """Initialize connection pool."""
        self._connected = True
        print(f"  [Connector] {self.name}: Connected to {self.config.base_url}")

    async def disconnect(self):
        """Close connection pool."""
        self._connected = False
        print(f"  [Connector] {self.name}: Disconnected")

    async def health_check(self) -> bool:
        """Check if API is reachable."""
        return self._connected

    async def get_data(self, endpoint: str) -> Optional[dict]:
        """
        Fetch data from API endpoint.

        Usage pattern:
            data = await self.connector_instances['API'].get_data('/stocks')
        """
        if not self._connected:
            raise RuntimeError(f"{self.name} not connected")

        # Simulated responses
        responses = {
            "/stocks": {"stocks": [{"symbol": "AAPL", "price": 150.0}]},
            "/stock/AAPL": {"symbol": "AAPL", "price": 150.0, "change": 2.5},
            "/indicators": {"indicators": ["PE", "EPS", "Revenue"]},
            "/health": {"status": "healthy"},
        }

        return responses.get(endpoint)

    async def post_data(self, endpoint: str, data: dict) -> dict:
        """Post data to API endpoint."""
        if not self._connected:
            raise RuntimeError(f"{self.name} not connected")
        return {"success": True, "endpoint": endpoint, "received": data}


class SimulatedSQLConnector:
    """
    Simulated SQL connector for demonstration.

    In production, use blazing.SQLAlchemyConnector which provides:
    - Async session factory
    - Connection pooling
    - Transaction management
    """

    def __init__(self, config: SQLConnectorConfig):
        self.config = config
        self.name = config.name
        self._connected = False
        self._data = {}

    async def connect(self):
        """Initialize database connection pool."""
        self._connected = True
        print(f"  [Connector] {self.name}: Connected to {self.config.address}/{self.config.dbname}")

    async def disconnect(self):
        """Close database connections."""
        self._connected = False
        print(f"  [Connector] {self.name}: Disconnected")

    async def health_check(self) -> bool:
        """Check database connectivity."""
        return self._connected

    async def execute(self, query: str, params: dict = None) -> list:
        """Execute a query and return results."""
        if not self._connected:
            raise RuntimeError(f"{self.name} not connected")

        # Simulated query results
        if "SELECT" in query.upper():
            return [{"id": 1, "value": "test"}, {"id": 2, "value": "demo"}]
        return []

    async def insert(self, table: str, records: list) -> int:
        """Insert records into table."""
        if not self._connected:
            raise RuntimeError(f"{self.name} not connected")
        return len(records)


# =============================================================================
# Service Using Connectors
# =============================================================================

class MarketDataService(BaseService):
    """
    Service that uses multiple connectors to fetch and store market data.

    Pattern:
        class TradeGrid(BaseService):
            def __init__(self, connector_instances):
                self.connector_instances = connector_instances

            async def _add_stock_price(self, stock_id):
                data = await self.connector_instances['GuruFocus'].get_data(url)
                ...
    """

    def __init__(self, connector_instances: dict):
        self.connector_instances = connector_instances

    async def _async_init(self):
        """Connect all connectors during service initialization."""
        for name, connector in self.connector_instances.items():
            if hasattr(connector, 'connect'):
                await connector.connect()

    async def health_check(self) -> dict:
        """Check health of all connectors."""
        results = {}
        for name, connector in self.connector_instances.items():
            if hasattr(connector, 'health_check'):
                results[name] = await connector.health_check()
        return results

    async def get_stock_data(self, symbol: str) -> Optional[dict]:
        """Fetch stock data from REST API."""
        api = self.connector_instances.get('MarketAPI')
        if not api:
            return None
        return await api.get_data(f"/stock/{symbol}")

    async def get_all_stocks(self) -> list:
        """Fetch all stocks from API."""
        api = self.connector_instances.get('MarketAPI')
        if not api:
            return []
        data = await api.get_data("/stocks")
        return data.get("stocks", []) if data else []

    async def save_stock_data(self, records: list) -> int:
        """Save stock data to database."""
        db = self.connector_instances.get('Database')
        if not db:
            return 0
        return await db.insert("stock_prices", records)

    async def fetch_and_store(self, symbol: str) -> dict:
        """
        Fetch stock data from API and store in database.

        This demonstrates the common pattern of using multiple connectors
        in a single operation.
        """
        # Fetch from API
        data = await self.get_stock_data(symbol)
        if not data:
            return {"success": False, "error": "Failed to fetch data"}

        # Store in database
        inserted = await self.save_stock_data([data])

        return {
            "success": True,
            "symbol": symbol,
            "data": data,
            "records_inserted": inserted
        }


# =============================================================================
# Main Demo
# =============================================================================

async def main():
    """Demonstrate connector integration patterns."""
    print("=" * 60)
    print("Connector Integration Patterns Demo")
    print("=" * 60)

    # Define connector configurations
    rest_config = RESTConnectorConfig(
        name="MarketAPI",
        base_url="https://api.marketdata.example.com",
        auth={"token": "demo-api-key"},
        throttle_limit=10,
        throttle_window=1,
        throttle_mode="fixed"
    )

    sql_config = SQLConnectorConfig(
        name="Database",
        address="localhost:5432",
        dbname="market_data",
        user="app_user",
        password="secret"
    )

    print("\n1. Connector Configurations")
    print("-" * 40)
    print(f"  REST: {rest_config.name} -> {rest_config.base_url}")
    print(f"    Throttle: {rest_config.throttle_limit} req/{rest_config.throttle_window}s")
    print(f"  SQL:  {sql_config.name} -> {sql_config.address}/{sql_config.dbname}")

    # Create connectors
    print("\n2. Creating Connectors")
    print("-" * 40)
    rest_connector = SimulatedRESTConnector(rest_config)
    sql_connector = SimulatedSQLConnector(sql_config)

    # Create service with connectors
    connector_instances = {
        "MarketAPI": rest_connector,
        "Database": sql_connector
    }

    print("\n3. Initializing Service")
    print("-" * 40)
    service = await MarketDataService.create(connector_instances)

    # Health check
    print("\n4. Health Check")
    print("-" * 40)
    health = await service.health_check()
    for name, status in health.items():
        status_str = "OK" if status else "FAILED"
        print(f"  {name}: {status_str}")

    # Fetch data
    print("\n5. Fetch Stock Data")
    print("-" * 40)
    stocks = await service.get_all_stocks()
    print(f"  Fetched {len(stocks)} stocks: {stocks}")

    # Fetch and store
    print("\n6. Fetch and Store Operation")
    print("-" * 40)
    result = await service.fetch_and_store("AAPL")
    print(f"  Success: {result['success']}")
    print(f"  Data: {result.get('data')}")
    print(f"  Records inserted: {result.get('records_inserted')}")

    # Cleanup
    print("\n7. Cleanup")
    print("-" * 40)
    await rest_connector.disconnect()
    await sql_connector.disconnect()

    print("\n" + "=" * 60)
    print("Key Patterns:")
    print("=" * 60)
    print("  1. Connectors encapsulate external service access")
    print("  2. Services receive connector_instances dict")
    print("  3. Services use connectors via self.connector_instances['name']")
    print("  4. Health checks verify all connector connectivity")
    print("  5. Multiple connectors can be used in single operations")


if __name__ == "__main__":
    asyncio.run(main())
