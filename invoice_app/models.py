import decimal
from django.db import models
from django.utils import timezone

class Customer(models.Model):
    """Stores customer information."""
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True, help_text="Customer's unique email address.")
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Invoice(models.Model):
    """
    Stores the main invoice data, linking a customer to a set of items.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PAID', 'Paid'),
        ('UNPAID', 'Unpaid'),
        ('CANCELLED', 'Cancelled'),
    ]

    # Core Invoice Details
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    invoice_number = models.CharField(max_length=50, unique=True)
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    
    # Financial Details
    shipping_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=decimal.Decimal('0.00')
    )
    payment_method = models.CharField(max_length=50, default='Not Specified', blank=True)

    # Additional Information
    notes = models.TextField(blank=True, help_text="Internal notes or terms and conditions for the customer.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Invoice {self.invoice_number} for {self.customer}"

    @property
    def subtotal(self):
        """Calculates the sum of all item totals before shipping or taxes."""
        return sum(item.total_price for item in self.items.all())

    @property
    def total(self):
        """Calculates the final total, including shipping costs."""
        return self.subtotal + self.shipping_cost

class InvoiceItem(models.Model):
    """Represents a single line item on an invoice."""
    invoice = models.ForeignKey(
        Invoice, 
        on_delete=models.CASCADE, 
        related_name='items' # This allows using `invoice.items.all()`
    )
    description = models.CharField(max_length=255, help_text="Description of the product or service.")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="Price per unit."
    )

    def __str__(self):
        return f"{self.quantity} x {self.description}"

    @property
    def total_price(self):
        """Calculates the total price for this line item (quantity * unit_price)."""
        return self.quantity * self.unit_price

