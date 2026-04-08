import csv
import io
import random

from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def download_csv(file_key: str, services=None):
        """Download CSV file (simulated)."""
        # In production, use: return await services["FileStorageService"].download(file_key)
        # Simulate CSV content
        csv_content = """name,email,department
John Doe,john@example.com,Engineering
Jane Smith,jane@example.com,Marketing
Bob Wilson,,Sales
Alice Brown,alice@example.com,Engineering
"""
        return csv_content.encode("utf-8")

    @app.step
    async def parse_csv(file_content: bytes, services=None):
        """Parse CSV file."""
        content = file_content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        return {"rows": rows, "count": len(rows)}

    @app.step
    async def validate_csv_rows(rows: list, services=None):
        """Validate CSV rows."""
        valid_rows = []
        errors = []
        for idx, row in enumerate(rows):
            try:
                # Validate required fields
                if not row.get("email") or not row.get("name"):
                    raise ValueError("Missing required fields")
                valid_rows.append(row)
            except ValueError as e:
                errors.append({"row": idx, "error": str(e)})
        return {"valid": valid_rows, "errors": errors}

    @app.step
    async def import_csv_rows(rows: list, services=None):
        """Import validated rows to database (simulated)."""
        # In production, use: await services["UserDatabase"].create_user(row["name"], row["email"])
        imported = []
        for row in rows:
            user_id = random.randint(1000, 9999)
            imported.append(user_id)
            print(f"[Simulated] Created user: {row['name']} ({row['email']}) -> ID: {user_id}")
        return {"imported": len(imported), "ids": imported}

    @app.workflow
    async def import_csv_file(file_key: str, services=None):
        """Import CSV file."""
        # Download file
        file_content = await download_csv(file_key, services=services)
        # Parse CSV
        parsed = await parse_csv(file_content, services=services)
        # Validate rows
        validated = await validate_csv_rows(parsed["rows"], services=services)
        # Import valid rows
        result = await import_csv_rows(validated["valid"], services=services)
        return {
            "file": file_key,
            "total_rows": parsed["count"],
            "imported": result["imported"],
            "errors": len(validated["errors"]),
        }

    await app.publish()

    # Execute the CSV import workflow
    print("Importing CSV file...")
    result = await app.import_csv_file(file_key="users/import.csv").wait_result()

    print(f"\nCSV Import completed!")
    print(f"  File: {result['file']}")
    print(f"  Total rows: {result['total_rows']}")
    print(f"  Imported: {result['imported']}")
    print(f"  Errors: {result['errors']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
