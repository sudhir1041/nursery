
from django.contrib import admin
from .models import Order, Invoice

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('invoice_id', 'order_id', 'customer_name', 'order_total', 'order_status', 'order_date')
    list_filter = ('order_status', 'order_shipment_status', 'payment_method')
    search_fields = ('invoice_id', 'order_id', 'customer_name', 'customer_email')
    readonly_fields = ('invoice_id',)
    ordering = ('-order_date',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'order', 'invoice_date', 'created_at')
    list_filter = ('invoice_date', 'created_at')
    search_fields = ('invoice_number', 'order__invoice_id')
    readonly_fields = ('invoice_number', 'created_at', 'updated_at')
    ordering = ('-invoice_date',)