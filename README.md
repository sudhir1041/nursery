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
2. Apply migrations and create a superuser:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
3. Run the development server:
   ```bash
   python manage.py runserver
   ```

After logging into the Django admin site you can manage WooCommerce and Shopify
API credentials, logos and invoicing company details under **Site Settings**.


## Logging

The project writes log files to the `logs/` folder. Log configuration resides in `nurseryproject/settings.py`.

## License

No license file is provided.
