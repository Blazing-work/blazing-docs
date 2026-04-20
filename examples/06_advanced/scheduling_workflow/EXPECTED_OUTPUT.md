# Expected Output

## Running

```bash
python flow.py
```

## Output

```
Scheduled workflows registered:
  - hourly_report: Every hour at :00
  - sync_data: Every 30 minutes
  - daily_summary: Weekdays at 9am
  - frequent_check: Every 15 minutes (ET)

Schedules are now active on the Blazing backend.
```

## Notes

- Schedules are defined using `Cron` or `Period` classes from the `blazing` SDK
- The `schedule` parameter is passed to the `@app.workflow()` decorator
- **Cron expressions** use standard 5-field format: `minute hour day-of-month month day-of-week`
  - `"0 * * * *"` - Every hour at minute 0
  - `"*/15 * * * *"` - Every 15 minutes
  - `"0 9 * * 1-5"` - 9am on weekdays (Monday=1, Sunday=0)
  - `"0 0 1 * *"` - Midnight on the 1st of each month
- **Period intervals** use time units: `seconds`, `minutes`, `hours`, `days`
  - `Period(minutes=30)` - Every 30 minutes
  - `Period(hours=1)` - Every hour
  - `Period(days=1)` - Daily
  - `Period(hours=1, jitter_seconds=60)` - Every hour with ±60s jitter
- Cron schedules support optional timezone with `tz` parameter (e.g., `"US/Eastern"`)
- Schedules are server-side: they run on the Blazing backend after `app.publish()`
- No need to keep the client script running - schedules persist on the backend
- Scheduled workflows automatically retry on failure (default retry policy)
- Use Period with jitter to prevent thundering herd when multiple instances start simultaneously
