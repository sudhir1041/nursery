# invoice/admin.py

from django.contrib import admin
from .models import Customer, Invoice, InvoiceItem

class InvoiceItemInline(admin.TabularInline):
    """
    Allows editing of InvoiceItem objects directly within the Invoice admin page.
    """
    model = InvoiceItem
    extra = 1  # Number of empty forms to display
    readonly_fields = ('get_total',)
    
    def get_total(self, obj):
        return obj.get_total()
    get_total.short_description = 'Total'

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the Invoice model.
    """
    list_display = ('invoice_number', 'customer', 'issue_date', 'due_date', 'status', 'get_total')
    list_filter = ('status', 'issue_date')
    search_fields = ('invoice_number', 'customer__name')
    readonly_fields = ('get_total', 'created_at', 'updated_at')
    inlines = [InvoiceItemInline]

    def get_total(self, obj):
        return f"₹{obj.get_total():.2f}"
    get_total.short_description = 'Total Amount'

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the Customer model.
    """
    list_display = ('name', 'email', 'phone')
    search_fields = ('name', 'email')

# The InvoiceItem model is managed through the InvoiceAdmin, so a separate registration is not needed.
# However, if you wanted to manage it separately, you could use:
# @admin.register(InvoiceItem)
# class InvoiceItemAdmin(admin.ModelAdmin):
#     list_display = ('invoice', 'description', 'quantity', 'unit_price')

