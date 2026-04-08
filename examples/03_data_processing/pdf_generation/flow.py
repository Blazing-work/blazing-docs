from blazing import Blazing


async def main():
    app = Blazing()  # Uses Blazing SaaS by default

    @app.step
    async def generate_invoice_data(order_id: str, services=None):
        """Fetch data for invoice (simulated)."""
        # In production, fetch from database via services
        return {
            "order": {"id": order_id, "date": "2025-12-10", "customer_id": 123},
            "customer": {"name": "John Doe", "email": "john@example.com"},
            "items": [
                {"name": "Widget A", "price": 29.99, "qty": 2},
                {"name": "Widget B", "price": 49.99, "qty": 1},
            ],
            "total": 109.97,
        }

    @app.step
    async def render_pdf(data: dict, template: str, services=None):
        """Render PDF from template (simulated)."""
        # In production, use WeasyPrint or similar:
        # from weasyprint import HTML
        # html_content = await services["TemplateService"].render(template, data)
        # return HTML(string=html_content).write_pdf()

        # Simulated PDF bytes (in production, this would be actual PDF content)
        pdf_content = f"""
        INVOICE #{data['order']['id']}
        Date: {data['order']['date']}
        Customer: {data['customer']['name']}

        Items:
        {chr(10).join(f"  - {item['name']}: ${item['price']} x {item['qty']}" for item in data['items'])}

        Total: ${data['total']}
        """.encode("utf-8")
        return pdf_content

    @app.step
    async def upload_invoice(order_id: str, pdf_bytes: bytes, services=None):
        """Upload invoice to storage (simulated)."""
        # In production, use: await services["FileStorageService"].upload(file_key, pdf_bytes)
        file_key = f"invoices/{order_id}.pdf"
        print(f"[Simulated] Uploading {len(pdf_bytes)} bytes to {file_key}")
        return {"url": f"https://storage.example.com/{file_key}", "file_key": file_key}

    @app.workflow
    async def create_invoice(order_id: str, services=None):
        """Generate and store invoice PDF."""
        data = await generate_invoice_data(order_id, services=services)
        pdf_bytes = await render_pdf(data, "invoice_template.html", services=services)
        result = await upload_invoice(order_id, pdf_bytes, services=services)

        return {
            "order_id": order_id,
            "invoice_url": result["url"],
            "total": data["total"],
        }

    await app.publish()

    # Execute the workflow
    print("Creating invoice for order ORD-12345...")
    result = await app.create_invoice(order_id="ORD-12345").wait_result()

    print(f"\nInvoice created!")
    print(f"  Order ID: {result['order_id']}")
    print(f"  Invoice URL: {result['invoice_url']}")
    print(f"  Total: ${result['total']}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
