# Nursery Nisarga Dashboard

This Django project collects and manages orders from multiple e‑commerce platforms and integrates them into a single administration dashboard.

## Key Features

- **Order Sources** – Synchronises orders from WooCommerce, Shopify and Facebook.
- **Dashboard & Reports** – Displays combined counts of pending, shipped and unshipped orders.
- **Shipment Workflow** – Views for marking shipments and tracking outstanding items.
- **Invoices** – The `invoice_app` builds PDF invoices for any order.
- **WhatsApp Integration** – Uses Channels and Celery to handle WhatsApp messages and marketing campaigns.
- **Webhooks** – Endpoints for Shopify and WooCommerce to push updates.
- **Celery Tasks** – Redis‑backed task queue for asynchronous processing.

## Project Layout

```
manage.py              Django management script
nurseryproject/        Core settings, URLs and dashboard views
facebook_app/          Facebook order models and webhooks
shopify_app/           Shopify order models, forms and utilities
woocommerce_app/       WooCommerce order and product models
invoice_app/           Invoice generation logic
whatsapp_app/          WhatsApp models, consumers and Celery tasks
shipment_app/          Views for pending and shipped orders
templates/             HTML templates
logs/                  Application logs
```

## Setup

1. Create and activate a virtual environment then install requirements:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Provide a `.env` file in the project root containing values referenced in `nurseryproject/settings.py`. Common variables include database credentials (`DB_NAME`, `DB_USER`, etc.), API keys (`SHOPIFY_API_KEY`, `WOOCOMMERCE_CONSUMER_KEY`, `WHATSAPP_ACCESS_TOKEN`) and the Django secret key.
3. Apply migrations and create a superuser:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
4. Run the development server:
   ```bash
   python manage.py runserver
   ```

For background tasks you also need Redis running and Celery workers:
```bash
celery -A nurseryproject worker -l info
celery -A nurseryproject beat -l info
```

## Logging

The project writes log files to the `logs/` folder. Log configuration resides in `nurseryproject/settings.py`.

## License

No license file is provided.

## Ecommerce Management API

A streamlined API-only Django project located in `ecommerce_management/`. It excludes Celery, Channels and WhatsApp integrations. Credentials are stored through the `settings_app` API rather than environment files. A minimal React frontend is provided in `ecommerce_management/frontend/` to demonstrate integration with the API.

Available API endpoints include:

- `/api/settings/` - manage credentials
- `/api/whatsapp/` - WhatsApp contacts
- `/api/facebook/` - Facebook orders
- `/api/shopify/` - Shopify orders
- `/api/woocommerce/` - WooCommerce orders
- `/api/invoice/` - invoice orders

### Email reports

Configure SMTP credentials using the `/api/settings/` endpoint with keys like `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `REPORT_RECIPIENT_EMAIL`.
Run the management command below daily (e.g. via cron at 8pm) to send order summaries:
```bash
python ecommerce_management/manage.py send_eod_report
```
Invoices created through the `/api/invoice/` endpoint are automatically emailed to the customer address if provided.

To install dependencies for the new project:
```bash
pip install -r ecommerce_management/requirements.txt
```

Run migrations and start the development server:
```bash
python ecommerce_management/manage.py migrate
python ecommerce_management/manage.py runserver
```
