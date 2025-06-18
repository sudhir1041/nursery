# Nursery Nisarga Dashboard

This Django project collects and manages orders from multiple e‑commerce platforms and integrates them into a single administration dashboard.

## Key Features

- **Order Sources** – Synchronises orders from WooCommerce, Shopify and Facebook.
- **Dashboard & Reports** – Displays combined counts of pending, shipped and unshipped orders.
- **Shipment Workflow** – Views for marking shipments and tracking outstanding items.
- **Invoices** – The `invoice_app` builds PDF invoices for any order.
- **Webhooks** – Endpoints for Shopify and WooCommerce to push updates.

## Project Layout

```
manage.py              Django management script
nurseryproject/        Core settings, URLs and dashboard views
facebook_app/          Facebook order models and webhooks
shopify_app/           Shopify order models, forms and utilities
woocommerce_app/       WooCommerce order and product models
invoice_app/           Invoice generation logic
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
2. Provide a `.env` file in the project root containing values referenced in `nurseryproject/settings.py`. Common variables include database credentials (`DB_NAME`, `DB_USER`, etc.), API keys (`SHOPIFY_API_KEY`, `WOOCOMMERCE_CONSUMER_KEY`) and the Django secret key.
3. Apply migrations and create a superuser:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
4. Run the development server:
   ```bash
   python manage.py runserver
   ```


## Logging

The project writes log files to the `logs/` folder. Log configuration resides in `nurseryproject/settings.py`.

## License

No license file is provided.
