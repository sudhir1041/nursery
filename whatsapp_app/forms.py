from django import forms
from django.core.exceptions import ValidationError
from .models import (
    WhatsAppSettings, MarketingCampaign, MarketingTemplate,
    BotResponse, AutoReply,Contact
)

# --- Settings Form ---
class WhatsAppSettingsForm(forms.ModelForm):
    """Form for managing WhatsApp Cloud API credentials and webhook settings."""
    class Meta:
        model = WhatsAppSettings
        fields = [
            'account_name',
            'whatsapp_token',
            'phone_number_id',
            'whatsapp_business_account_id',
            'app_id',
            'webhook_verify_token',
            'webhook_url', # Consider making this read-only or validating format
            'is_live_mode',
        ]
        widgets = {
            # Use PasswordInput for the token, render_value=False hides existing value
            'whatsapp_token': forms.PasswordInput(render_value=False, attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
            # Webhook token is usually auto-generated and shouldn't be changed lightly
            'webhook_verify_token': forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control'}),
            'account_name': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}), # Usually fixed
            'phone_number_id': forms.TextInput(attrs={'class': 'form-control'}),
            'whatsapp_business_account_id': forms.TextInput(attrs={'class': 'form-control'}),
            'app_id': forms.TextInput(attrs={'class': 'form-control'}),
            'webhook_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://yourdomain.com/whatsapp/webhook/'}),
            'is_live_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'account_name': 'Internal identifier for these settings.',
            'webhook_verify_token': 'Auto-generated. Use this value when setting up the webhook in the Meta Developer Portal.',
            'webhook_url': 'The full, public HTTPS URL where WhatsApp will send notifications. Must match the URL configured in Meta.',
            'whatsapp_token': 'Your WhatsApp Cloud API access token. Keep this confidential.',
            'phone_number_id': 'The ID associated with the phone number you are using via the API.',
            'whatsapp_business_account_id': 'Your main WhatsApp Business Account (WABA) ID.',
            'is_live_mode': 'Indicates if these credentials are for production use.',
        }

    # Example clean method for validation
    def clean_webhook_url(self):
        """Validate webhook URL format."""
        url = self.cleaned_data.get('webhook_url')
        if url and not url.startswith('https://'):
            raise ValidationError("Webhook URL must start with 'https://'.")
        # Add more specific URL validation if needed
        return url

# --- Manual Message Form (for Chat Detail page) ---
class ManualMessageForm(forms.Form):
    """Form for sending a single text message from the chat interface."""
    text_content = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Type your message here...',
            'class': 'form-control',
            'aria-label': 'Message content' # Accessibility
            }),
        label="", # Hide default label, use placeholder and aria-label
        required=True
    )
    # Consider adding fields for sending templates or media manually if needed
    # template_to_send = forms.ModelChoiceField(queryset=MarketingTemplate.objects.all(), required=False)
    # media_file = forms.FileField(required=False)

# --- Marketing Campaign Form ---
class MarketingCampaignForm(forms.ModelForm):
    """Form for creating or editing a marketing campaign using custom CSS classes."""
    # Fetch only templates relevant for marketing/utility
    template = forms.ModelChoiceField(
        # CORRECTED: Removed the non-existent 'status' filter
        queryset=MarketingTemplate.objects.filter(category__in=['MARKETING', 'UTILITY']),
        # Use custom 'form-select' class (needs styling in CSS)
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="-- Select an Approved Template --",
        required=True,
        help_text="Choose the pre-approved WhatsApp template for this campaign."
        # Note: If you need to filter by approval status,
        # you'll need to ensure your MarketingTemplate model HAS a status field
        # (e.g., status = models.CharField(max_length=20, choices=TEMPLATE_STATUS_CHOICES, default='PENDING'))
        # and then you could add status='APPROVED' back to the filter.
    )

    class Meta:
        model = MarketingCampaign
        fields = ['name', 'template'] # Only allow setting name and template initially
        widgets = {
             # Use custom 'form-input' class
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., Spring Plant Sale Promotion'}),
        }
        labels = {
            'name': 'Campaign Name',
        }
        help_texts = {
            'name': 'Give this campaign a descriptive internal name.',
        }

    # Optional: Add validation if needed
    # def clean_name(self):
    #     name = self.cleaned_data.get('name')
    #     if not name or len(name) < 3:
    #          raise forms.ValidationError("Campaign name must be at least 3 characters long.")
    #     # Check for uniqueness if required
    #     # if MarketingCampaign.objects.filter(name=name).exists():
    #     #     raise forms.ValidationError("A campaign with this name already exists.")
    #     return name



# --- Contact Upload Form (for Marketing Campaigns) ---
class ContactUploadForm(forms.Form):
    """Form for uploading a CSV file of contacts for a campaign."""
    contact_file = forms.FileField(
        label='Upload Contacts CSV File',
        help_text="CSV file must have a header row including 'wa_id'. Optional columns: 'name', 'var1', 'var2', etc. Variables map to template placeholders {{1}}, {{2}}.",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.csv'}), # Restrict file type in browser
        required=True
    )

    # Add clean method to validate file extension server-side as well
    def clean_contact_file(self):
        """Validate that the uploaded file is a CSV."""
        file = self.cleaned_data.get('contact_file')
        if file:
            if not file.name.lower().endswith('.csv'):
                raise ValidationError("Invalid file type. Please upload a .csv file.")
            # Optional: Add check for file size limit
            # if file.size > MAX_UPLOAD_SIZE:
            #     raise ValidationError(f"File size cannot exceed {MAX_UPLOAD_SIZE_MB} MB.")
        return file


# --- Bot Response Form (Optional, if using dedicated views instead of Admin) ---
class BotResponseForm(forms.ModelForm):
    """Form for creating/editing chatbot responses using custom CSS classes."""
    class Meta:
        model = BotResponse
        fields = ['trigger_phrase', 'response_text', 'is_active']
        widgets = {
            # Use custom 'form-input' class
            'trigger_phrase': forms.TextInput(attrs={'class': 'form-input'}),
            # Use custom 'form-input' class for textarea
            'response_text': forms.Textarea(attrs={'rows': 4, 'class': 'form-input'}),
            # Use custom 'form-checkbox-input' class
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox-input'}),
        }
        help_texts = {
            'trigger_phrase': 'The exact phrase (case-insensitive) the user must type to trigger this response.',
            'response_text': 'The message that will be sent back automatically.',
            'is_active': 'Enable this response.',
        }

    # Optional: Add custom validation if needed
    # def clean_trigger_phrase(self):
    #     data = self.cleaned_data['trigger_phrase']
    #     # Example validation: ensure it's not empty after stripping whitespace
    #     if not data.strip():
    #         raise forms.ValidationError("Trigger phrase cannot be empty.")
    #     return data


# --- Auto-Reply Settings Form (Optional, if using dedicated views instead of Admin) ---
class AutoReplySettingsForm(forms.ModelForm):
    """Form for managing the out-of-office auto-reply message using custom CSS classes."""
    class Meta:
        model = AutoReply # Ensure this model exists and is imported
        fields = ['message_text', 'is_active']
        widgets = {
             # Use custom 'form-input' class for textarea
            'message_text': forms.Textarea(attrs={'rows': 4, 'class': 'form-input'}),
             # Use custom 'form-checkbox-input' class
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox-input'}),
        }
        help_texts = {
            'message_text': 'The message sent when staff are unavailable (availability logic defined elsewhere).',
            'is_active': 'Enable the auto-reply feature.',
        }

    # Override save method or use signals if implementing singleton pattern
    # def save(self, commit=True):
    #     # Ensure only one instance exists
    #     # self.instance.pk = 1 # Assuming singleton with pk=1
    #     # return super().save(commit=commit)
# Add new Conatct form
class AddContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['wa_id', 'name']
        widgets = {
            'wa_id': forms.TextInput(attrs={'placeholder': 'e.g., 919876543210'}),
            'name': forms.TextInput(attrs={'required': False, 'placeholder': 'Optional profile name'}),
        }
        help_texts = {
            'wa_id': 'WhatsApp ID (Phone number with country code). Must be unique.',
        }

