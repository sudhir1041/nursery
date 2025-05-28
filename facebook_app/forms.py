from django import forms
from .models import Facebook_orders
import json 

class FacebookOrderForm(forms.ModelForm):

    INDIAN_STATES = [
        ('', 'Select State'),
        ('AN', 'Andaman and Nicobar Islands'),
        ('AP', 'Andhra Pradesh'),
        ('AR', 'Arunachal Pradesh'),
        ('AS', 'Assam'),
        ('BR', 'Bihar'),
        ('CH', 'Chandigarh'),
        ('CT', 'Chhattisgarh'),
        ('DN', 'Dadra and Nagar Haveli'),
        ('DD', 'Daman and Diu'),
        ('DL', 'Delhi'),
        ('GA', 'Goa'),
        ('GJ', 'Gujarat'),
        ('HR', 'Haryana'),
        ('HP', 'Himachal Pradesh'),
        ('JK', 'Jammu and Kashmir'),
        ('JH', 'Jharkhand'),
        ('KA', 'Karnataka'),
        ('KL', 'Kerala'),
        ('LA', 'Ladakh'),
        ('LD', 'Lakshadweep'),
        ('MP', 'Madhya Pradesh'),
        ('MH', 'Maharashtra'),
        ('MN', 'Manipur'),
        ('ML', 'Meghalaya'),
        ('MZ', 'Mizoram'),
        ('NL', 'Nagaland'),
        ('OR', 'Odisha'),
        ('PY', 'Puducherry'),
        ('PB', 'Punjab'),
        ('RJ', 'Rajasthan'),
        ('SK', 'Sikkim'),
        ('TN', 'Tamil Nadu'),
        ('TG', 'Telangana'),
        ('TR', 'Tripura'),
        ('UP', 'Uttar Pradesh'),
        ('UT', 'Uttarakhand'),
        ('WB', 'West Bengal')
    ]

    INDIAN_CITIES = [
        ('', 'Select City'),
        ('Mumbai', 'Mumbai'),
        ('Delhi', 'Delhi'),
        ('Bangalore', 'Bangalore'),
        ('Hyderabad', 'Hyderabad'),
        ('Chennai', 'Chennai'),
        ('Kolkata', 'Kolkata'),
        ('Pune', 'Pune'),
        ('Ahmedabad', 'Ahmedabad'),
        ('Jaipur', 'Jaipur'),
        ('Surat', 'Surat'),
        ('Lucknow', 'Lucknow'),
        ('Kanpur', 'Kanpur'),
        ('Nagpur', 'Nagpur'),
        ('Indore', 'Indore'),
        ('Thane', 'Thane'),
        ('Bhopal', 'Bhopal'),
        ('Visakhapatnam', 'Visakhapatnam'),
        ('Patna', 'Patna'),
        ('Vadodara', 'Vadodara'),
        ('Ghaziabad', 'Ghaziabad'),
        ('Ludhiana', 'Ludhiana'),
        ('Agra', 'Agra'),
        ('Nashik', 'Nashik'),
        ('Faridabad', 'Faridabad'),
        ('Meerut', 'Meerut'),
        ('Rajkot', 'Rajkot'),
        ('Kalyan', 'Kalyan'),
        ('Vasai', 'Vasai'),
        ('Varanasi', 'Varanasi')
    ]

    PAYMENT_METHODS = [
        ('', 'Select Payment Method'),
        ('phonepe', 'PhonePe'),
        ('paytm', 'Paytm'),
        ('googlepay', 'Google Pay'),
        ('cash', 'Cash'),
        ('nursery_nisarga', 'Nursery Nisarga')
    ]

    PLATFORMS = [
        ('', 'Select Platform'),
        ('facebook', 'Facebook'),
        ('woocommerce', 'WooCommerce'),
        ('shopify', 'Shopify'),
        ('offline', 'Offline')
    ]

    order_id = forms.CharField(widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    billing_state = forms.ChoiceField(choices=INDIAN_STATES, widget=forms.Select(attrs={'class': 'form-control'}))
    billing_city = forms.ChoiceField(choices=INDIAN_CITIES, widget=forms.Select(attrs={'class': 'form-control'}))
    mode_of_payment = forms.ChoiceField(choices=PAYMENT_METHODS, widget=forms.Select(attrs={'class': 'form-control'}))
    plateform = forms.ChoiceField(choices=PLATFORMS, widget=forms.Select(attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:  # Only for new instances
            from datetime import datetime
            today = datetime.now().strftime('%d%Y%m')
            # Get the last order_id for today
            last_order = Facebook_orders.objects.filter(order_id__startswith=f'NS{today}').order_by('-order_id').first()
            if last_order:
                # Extract the number from the last order_id and increment
                last_num = int(last_order.order_id[10:])  # Skip NS + date
                new_num = last_num + 1
            else:
                new_num = 1
            # Generate new order_id with date
            self.initial['order_id'] = f'NS{today}{new_num}'   
             
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
