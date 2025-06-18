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
2. Create the database and run migrations. Configuration values like API keys can be entered through the **Settings** page once the server is running, removing the need for a local `.env` file.
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
