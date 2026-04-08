import asyncio
from datetime import datetime, timedelta

from blazing import Blazing
from blazing.base import BaseService


# Simulated session database
_sessions_db = [
    {"session_id": "sess_001", "user_id": 1, "last_activity": "2024-01-01T10:00:00"},
    {"session_id": "sess_002", "user_id": 2, "last_activity": "2024-01-05T14:30:00"},
    {"session_id": "sess_003", "user_id": 1, "last_activity": "2024-12-01T09:00:00"},
    {"session_id": "sess_004", "user_id": 3, "last_activity": "2024-01-10T16:45:00"},
    {"session_id": "sess_005", "user_id": 2, "last_activity": "2024-12-05T11:20:00"},
]


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.service
    class Database(BaseService):
        def __init__(self, connectors):
            # In production: self._db = connectors.get("postgres")
            pass

        async def execute(self, query, params):
            """Execute database query (simulated)."""
            await asyncio.sleep(0.1)  # Simulate DB latency

            # Simulate finding expired sessions
            if "SELECT" in str(query):
                cutoff = params.get("cutoff", "")
                expired = [
                    s for s in _sessions_db
                    if s["last_activity"] < cutoff
                ]
                # Return a mock result object
                class MockResult:
                    def fetchall(self):
                        return [(s["session_id"],) for s in expired]
                return MockResult()

            # Simulate delete
            elif "DELETE" in str(query):
                ids_to_delete = params.get("ids", [])
                for sid in ids_to_delete:
                    for i, sess in enumerate(_sessions_db):
                        if sess["session_id"] == sid:
                            print(f"  [DB] Deleted session: {sid}")
                            break

    @app.step
    async def find_expired_sessions(cutoff_date: str, services=None):
        """Find sessions older than cutoff date."""
        # In production:
        # query = text("""
        #     SELECT session_id FROM sessions
        #     WHERE last_activity < :cutoff
        #     LIMIT 1000
        # """)
        result = await services["Database"].execute(
            "SELECT session_id FROM sessions WHERE last_activity < :cutoff LIMIT 1000",
            {"cutoff": cutoff_date}
        )
        return [row[0] for row in result.fetchall()]

    @app.step
    async def delete_sessions(session_ids: list, services=None):
        """Delete expired sessions."""
        # In production:
        # query = text("DELETE FROM sessions WHERE session_id = ANY(:ids)")
        await services["Database"].execute(
            "DELETE FROM sessions WHERE session_id = ANY(:ids)",
            {"ids": session_ids}
        )
        return {"deleted": len(session_ids)}

    @app.workflow
    async def cleanup_expired_sessions(days_old: int = 30, services=None):
        """Clean up sessions older than N days."""
        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()

        # Find expired sessions
        session_ids = await find_expired_sessions(cutoff_date, services=services)

        if not session_ids:
            return {"deleted": 0, "message": "No expired sessions"}

        # Delete sessions
        result = await delete_sessions(session_ids, services=services)

        return {"cutoff_date": cutoff_date, "deleted": result["deleted"]}

    await app.publish()

    # Execute the workflow
    print("Running session cleanup job (sessions older than 30 days)...")
    result = await app.cleanup_expired_sessions(days_old=30).wait_result()

    print(f"\nCleanup Results:")
    print(f"  Cutoff Date: {result.get('cutoff_date', 'N/A')}")
    print(f"  Sessions Deleted: {result['deleted']}")
    if result['deleted'] == 0:
        print(f"  Message: {result.get('message', 'None')}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
