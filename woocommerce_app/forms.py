from django import forms
from .models import WooCommerceOrder

class OrderEditForm(forms.ModelForm):
    class Meta:
        model = WooCommerceOrder
        # Choose fields safe for LOCAL editing. Avoid editing core synced data
        # unless you have a clear strategy for handling overwrites or syncing back.
        fields = [
            # Example editable fields (adjust as needed):
            'customer_note', # Maybe allow editing the note locally?
            'status', # Editing status locally can be risky if it conflicts with Woo.
            'billing_first_name', # Editing billing/shipping might be overwritten.
            # Add any custom fields you might have added to your model for local use.
        ]
        # Optional: Add widgets for styling if using Bootstrap etc.
        widgets = {
            'customer_note': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }