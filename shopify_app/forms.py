# shopify_app/forms.py
from django import forms
from .models import ShopifyOrder

class ShopifyOrderEditForm(forms.ModelForm):
    class Meta:
        model = ShopifyOrder
        # --- Choose fields safe for LOCAL editing ---
        fields = [
            'internal_notes',
            # Add any other custom, local-only fields here.
            # WARNING: Avoid adding fields like 'financial_status', 'fulfillment_status',
            # 'total_price', address fields etc. unless you have a specific reason and
            # understand they might be overwritten by Shopify syncs.
        ]
        widgets = {
            'internal_notes': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            # Add styling widgets for other fields if needed
        }

