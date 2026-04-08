import asyncio

from blazing import Blazing
from blazing.base import BaseService


# Simulated databases for demonstration
_metrics_db = {
    "2024-01-15": {
        "order_count": 1523,
        "revenue": 45678.90,
        "active_users": 892,
    },
    "2024-01-16": {
        "order_count": 1687,
        "revenue": 52341.25,
        "active_users": 945,
    },
}
_config_db = {
    "report_recipients": ["ceo@example.com", "cfo@example.com", "analytics@example.com"],
}


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    # Simulated services
    @app.service
    class MetricsDatabase(BaseService):
        def __init__(self, connectors):
            pass

        async def get_by_date(self, date: str) -> dict:
            """Fetch metrics for date (simulated)."""
            await asyncio.sleep(0.1)
            # Return actual data or default
            return _metrics_db.get(date, {
                "order_count": 1000,
                "revenue": 30000.00,
                "active_users": 500,
            })

    @app.service
    class EmailService(BaseService):
        def __init__(self, connectors):
            pass

        async def send(self, to: str, subject: str, body: str):
            """Send email (simulated)."""
            await asyncio.sleep(0.05)
            print(f"  [EMAIL] Sent to {to}: {subject}")

    @app.service
    class ConfigService(BaseService):
        def __init__(self, connectors):
            pass

        async def get(self, key: str):
            """Get config value (simulated)."""
            return _config_db.get(key, [])

    @app.step
    async def fetch_daily_metrics(date: str, services=None):
        """Fetch metrics for date."""
        metrics = await services["MetricsDatabase"].get_by_date(date)

        return {
            "date": date,
            "total_orders": metrics["order_count"],
            "revenue": metrics["revenue"],
            "active_users": metrics["active_users"],
        }

    @app.step
    async def generate_report(metrics: dict, services=None):
        """Generate report from metrics."""
        report = f"""
Daily Report - {metrics["date"]}
================================
Total Orders: {metrics["total_orders"]:,}
Revenue: ${metrics["revenue"]:,.2f}
Active Users: {metrics["active_users"]:,}
        """
        return report

    @app.step
    async def distribute_report(report: str, recipients: list, services=None):
        """Email report to recipients."""
        tasks = [
            services["EmailService"].send(email, "Daily Report", report)
            for email in recipients
        ]
        await asyncio.gather(*tasks)
        return {"sent_to": len(recipients)}

    @app.workflow
    async def daily_report_job(date: str, services=None):
        """Generate and send daily report."""
        metrics = await fetch_daily_metrics(date, services=services)
        report = await generate_report(metrics, services=services)

        recipients = await services["ConfigService"].get("report_recipients")
        result = await distribute_report(report, recipients, services=services)

        return {"date": date, "recipients": result["sent_to"], "report": report}

    await app.publish()

    # Execute the workflow for a specific date
    report_date = "2024-01-15"
    print(f"Generating daily report for {report_date}...")

    result = await app.daily_report_job(date=report_date).wait_result()

    print(f"\nReport generated and sent to {result['recipients']} recipients")
    print("\n--- Generated Report ---")
    print(result['report'])


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
