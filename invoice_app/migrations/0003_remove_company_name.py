from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('invoice_app', '0002_invoice_payment_method_invoice_shipping_cost_and_more'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Company_name',
        ),
    ]
