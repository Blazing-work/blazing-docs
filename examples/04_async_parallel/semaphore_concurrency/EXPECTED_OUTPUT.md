# Expected Output

## Running

```bash
python flow.py
```

## Output

```
Fetching 5 users with max concurrency of 2...
Fetching user 1...
Fetching user 2...
Fetching user 3...
Fetching user 4...
Fetching user 5...

Fetched 5 users:
  - User1 (ID: 1)
  - User2 (ID: 2)
  - User3 (ID: 3)
  - User4 (ID: 4)
  - User5 (ID: 5)
```

## Notes

- The `Semaphore` is imported from `blazing` SDK, not from `asyncio`
- Semaphore limits the number of concurrent operations to the specified count (2 in this example)
- Even though we launch 5 tasks in parallel, only 2 run at a time
- This is useful for:
  - Rate-limiting API calls to avoid throttling
  - Limiting database connection pool usage
  - Preventing resource exhaustion
  - Controlling memory usage in data processing pipelines
- The `async with semaphore:` context manager acquires/releases the semaphore automatically
- Tasks queue up and wait for semaphore availability
- Total execution time is longer than fully parallel (3 seconds vs 1 second for 5 tasks) but prevents overload
