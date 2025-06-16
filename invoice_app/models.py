from django.db import models
import random
from django.utils import timezone
from datetime import datetime

class Order(models.Model):
    def generate_invoice_id():
        return str(random.randint(100000, 999999))
    invoice_id = models.CharField(max_length=6, default=generate_invoice_id, editable=False, unique=True)
    order_id = models.CharField(max_length=100, unique=True)
    order_date = models.DateTimeField(default=timezone.now)
    customer_name = models.CharField(max_length=200)
    customer_address = models.TextField()
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=15)
    order_total = models.DecimalField(max_digits=10, decimal_places=2)
    order_status = models.CharField(max_length=50, default='pending')
    order_items = models.JSONField(default=dict)
    order_shipment_status = models.CharField(max_length=50, default='pending')
    order_notes = models.TextField(blank=True, null=True)
    payment_method = models.CharField(max_length=100, default='cash')
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"Order {self.invoice_id}"

    def save(self, *args, **kwargs):
        if isinstance(self.order_date, str):
            try:
                self.order_date = datetime.fromisoformat(self.order_date)
            except (TypeError, ValueError):
                self.order_date = timezone.now()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-order_date']

class Company_name(models.Model):
    company_name = models.CharField(max_length=100)
    company_address = models.TextField()
    company_phone = models.CharField(max_length=15)
    company_email = models.EmailField()
    company_website = models.URLField()
    company_logo = models.ImageField(upload_to='company_logo/', blank=True, null=True)

    def __str__(self):
        return self.company_name
    class Meta:
        verbose_name_plural = 'Company Details'

class Invoice(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    invoice_date = models.DateTimeField(default=timezone.now)
    invoice_number = models.CharField(max_length=20, unique=True)
    pdf_file = models.FileField(upload_to='invoices/', blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice {self.invoice_number} for Order {self.order.invoice_id}"

    def generate_invoice_number(self):
        return f"INV-{self.order.invoice_id}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        if isinstance(self.invoice_date, str):
            try:
                self.invoice_date = datetime.fromisoformat(self.invoice_date)
            except (TypeError, ValueError):
                self.invoice_date = timezone.now()
        if isinstance(self.created_at, str):
            try:
                self.created_at = datetime.fromisoformat(self.created_at)
            except (TypeError, ValueError):
                self.created_at = timezone.now()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-invoice_date']

