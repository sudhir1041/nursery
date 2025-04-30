from django import forms
from .models import Facebook_orders
import json 

class FacebookOrderForm(forms.ModelForm):

    def clean_products_json(self):

        data = self.cleaned_data.get('products_json')

        if data is None or data == '':
            return []

        if not isinstance(data, list):
            
            try:
                data = json.loads(data)
                if not isinstance(data, list):
                     raise forms.ValidationError("Products data structure must be a JSON list.")
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format provided for products.")
            except TypeError: 
                 raise forms.ValidationError("Invalid data type received for products.")


        if not isinstance(data, list):
             raise forms.ValidationError("Products JSON must be a list (e.g., []).") 

        validated_products = []
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                raise forms.ValidationError(f"Item #{index+1} in products list must be a dictionary (e.g., {{...}}).")

            if 'product_name' not in item or not item['product_name']: 
                 raise forms.ValidationError(f"Item #{index+1}: 'product_name' is required.")
            if 'quantity' not in item:
                 raise forms.ValidationError(f"Item #{index+1}: 'quantity' is required.")
            if 'price' not in item:
                 raise forms.ValidationError(f"Item #{index+1}: 'price' is required.")

            try:

                qty = int(item['quantity'])
                if qty <= 0:
                    raise forms.ValidationError(f"Item #{index+1}: Quantity must be a positive integer.")
                item['quantity'] = qty 
            except (ValueError, TypeError):
                 raise forms.ValidationError(f"Item #{index+1}: Quantity must be a whole number.")

            try:
                
                price = float(item['price'])
                if price < 0:
                     raise forms.ValidationError(f"Item #{index+1}: Price cannot be negative.")
                item['price'] = price 
            except (ValueError, TypeError):
                 raise forms.ValidationError(f"Item #{index+1}: Price must be a number.")

            
            item['pot_size'] = item.get('pot_size', '') 

            validated_products.append(item) 
        
        return validated_products


    class Meta:
        model = Facebook_orders
        fields = [
            'order_id', 'status','shipment_status','billing_first_name', 'billing_last_name',
            'billing_email', 'billing_phone', 'alternet_number', 'billing_address',
            'billing_city', 'billing_state', 'billing_postcode', 'billing_country',
            'total_amount', 'shipment_amount', 'received_amount', 'credit_amount',
            'mode_of_payment', 'currency', 'customer_note', 'internal_notes',
            'tracking_info', 'products_json', 
            'plateform', 'date_created'
        ]
        widgets = {
            'date_created': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'customer_note': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'internal_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'tracking_info': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'billing_address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'products_json': forms.HiddenInput(),
        }
        help_texts = {
             'products_json': 'Add products using the "Add Product" button below. Data is saved automatically.',
        }