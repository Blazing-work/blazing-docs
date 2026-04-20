"""Scheduling Workflow Example

Demonstrates using Cron and Period schedules for periodic workflow execution
on the Blazing server.

Documentation: https://blazing.work/docs/advanced/scheduling
Related Examples: cli_publish_deploy, autoscaling_config
"""

from blazing import Blazing, Cron, Period
import asyncio
from datetime import datetime


async def main():
    app = Blazing()

    @app.step
    async def generate_report(report_type: str, services=None):
        """Generate a report of the specified type."""
        timestamp = datetime.utcnow().isoformat()
        return {
            "type": report_type,
            "generated_at": timestamp,
            "status": "completed",
            "records": 1234,
        }

    # Scheduled workflow using Cron expression
    # Runs every hour at minute 0
    @app.workflow(schedule=Cron("0 * * * *"))
    async def hourly_report(services=None):
        """Workflow that runs every hour."""
        report = await generate_report("hourly", services=services)
        print(f"Hourly report generated: {report['records']} records")
        return report

    # Scheduled workflow using Period
    # Runs every 30 minutes
    @app.workflow(schedule=Period(minutes=30))
    async def sync_data(services=None):
        """Workflow that runs every 30 minutes."""
        report = await generate_report("sync", services=services)
        print(f"Data sync completed: {report['records']} records")
        return report

    # Daily report at 9am on weekdays (Monday-Friday)
    @app.workflow(schedule=Cron("0 9 * * 1-5"))
    async def daily_summary(services=None):
        """Workflow that runs at 9am on weekdays."""
        report = await generate_report("daily", services=services)
        print(f"Daily summary generated: {report['records']} records")
        return report

    # Every 15 minutes with timezone
    @app.workflow(schedule=Cron("*/15 * * * *", tz="US/Eastern"))
    async def frequent_check(services=None):
        """Workflow that runs every 15 minutes in Eastern time."""
        report = await generate_report("frequent", services=services)
        print(f"Frequent check completed: {report['records']} records")
        return report

    await app.publish()

    print("Scheduled workflows registered:")
    print("  - hourly_report: Every hour at :00")
    print("  - sync_data: Every 30 minutes")
    print("  - daily_summary: Weekdays at 9am")
    print("  - frequent_check: Every 15 minutes (ET)")
    print("\nSchedules are now active on the Blazing backend.")


if __name__ == "__main__":
    asyncio.run(main())
