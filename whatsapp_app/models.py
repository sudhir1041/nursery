# whatsapp_app/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings # To potentially link to your project's User model

# --- Core WhatsApp Settings ---
class WhatsAppSettings(models.Model):
    """Stores WhatsApp Cloud API Credentials and settings for the nursery project."""
    account_name = models.CharField(
        max_length=100,
        verbose_name="Account Name",
        unique=True,
        default="NurseryProjectDefault",
        help_text="A unique name for these settings (e.g., main account)."
    )
    whatsapp_token = models.CharField(
        max_length=500,
        verbose_name="WhatsApp Token",
        help_text="Your WhatsApp Cloud API Access Token (Permanent or Temporary)."
    )
    phone_number_id = models.CharField(
        max_length=100,
        verbose_name="Phone Number ID",
        help_text="The Phone Number ID from your WhatsApp App settings in Meta Developer Portal."
    )
    whatsapp_business_account_id = models.CharField(
        max_length=100,
        verbose_name="WhatsApp Business Account ID",
        help_text="Your WhatsApp Business Account (WABA) ID."
    )
    app_id = models.CharField(
        max_length=100,
        verbose_name="App ID",
        blank=True,
        null=True,
        help_text="Your Facebook App ID (optional, used for some integrations)."
    )
    webhook_verify_token = models.CharField(
        max_length=100,
        verbose_name="Webhook Verify Token",
        default=uuid.uuid4,
        help_text="Auto-generated string used to verify webhook setup with Meta."
    )
    webhook_url = models.URLField(
        max_length=255,
        verbose_name="Webhook URL",
        blank=True,
        null=True,
        help_text="The public URL where WhatsApp will send incoming messages (e.g., https://yournursery.com/whatsapp/webhook/)."
    )
    MODE_CHOICES = [
        (False, 'Development Mode'),
        (True, 'Live Mode'),
    ]
    is_live_mode = models.BooleanField(
        default=False,
        choices=MODE_CHOICES,
        verbose_name="Live Mode",
        help_text="Check this box if these credentials are for the live production environment.",
    )

    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Check if these settings should be used for sending messages",
    )

    is_primary = models.BooleanField(
        default=False,
        verbose_name="Primary",
        help_text="Check if this is the main account.",

    )
    last_validated = models.DateTimeField(
        verbose_name="Last Validated",
        null=True,
        blank=True,
        help_text="Timestamp when these credentials were last known to be working."
    )

    def __str__(self):
        return f"WhatsApp Settings ({self.account_name})"

    class Meta:
        verbose_name = "WhatsApp Setting"
        verbose_name_plural = "WhatsApp Settings"
        # Consider adding constraints if only one instance should exist
        # constraints = [
        #     models.UniqueConstraint(fields=['id'], condition=models.Q(id=1), name='singleton_constraint')
        # ]

# --- Contact Information ---
class Contact(models.Model):
    """Represents a WhatsApp contact, potentially linked to a nursery customer."""
    phone = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="WhatsApp Number",
        help_text="Phone Number including country code, e.g., 919876543210."
    )

    # To mark if this is a real or dummy contact
    IS_REAL_CHOICES = [
        (True, 'Real'),
        (False, 'Dummy'),
    ]
    is_real = models.BooleanField(
        default=True,
        choices=IS_REAL_CHOICES,
        help_text="Is this contact a real person or dummy one?"
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Profile name obtained from WhatsApp (can change)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ***** Integration Point *****
    # Link to your existing Customer/User model if applicable
    # Example: Assuming you have a 'customers' app with a 'Customer' model
    # from customers.models import Customer # Ensure this app is above whatsapp_app in INSTALLED_APPS or handle circular imports
    # customer = models.ForeignKey(
    #    Customer,
    #    on_delete=models.SET_NULL, # Keep contact even if customer is deleted
    #    null=True,
    #    blank=True,
    #    related_name='whatsapp_contacts',
    #    help_text="Link to the main customer profile in the nursery system."
    # )

    # Example: Linking to Django's default User model (if staff uses WhatsApp)
    # user = models.OneToOneField(
    #    settings.AUTH_USER_MODEL,
    #    on_delete=models.SET_NULL,
    #    null=True,
    #    blank=True,
    #    related_name='whatsapp_contact'
    # )

    def __str__(self):
        display_name = self.name or self.phone
        # Add identifier from linked model if exists
        # if hasattr(self, 'customer') and self.customer:
        #     display_name += f" (Customer ID: {self.customer.pk})" # Adjust based on your Customer model
        # elif self.user:
        #      display_name += f" (User: {self.user.username})"
        return display_name

    class Meta:
        verbose_name = "WhatsApp Contact"
        verbose_name_plural = "WhatsApp Contacts"

    def save(self, *args, **kwargs):
        """
        Override the save method to validate phone format if provided
        """
        if self.phone and not self.phone.isdigit():
            raise ValueError("Phone number should only contain digits.")
        super(Contact, self).save(*args, **kwargs)

# --- Chat Message Log ---
class ChatMessage(models.Model):
    """Stores individual messages exchanged via WhatsApp."""
    MESSAGE_DIRECTION_CHOICES = [
        ('IN', 'Incoming'),
        ('OUT', 'Outgoing'),
    ]
    MESSAGE_STATUS_CHOICES = [
        ('PENDING', 'Pending Send'),       # Message created, about to be sent to API
        ('SENT', 'Sent to WhatsApp'),      # API accepted the message (got WAMID)
        ('DELIVERED', 'Delivered'),        # WhatsApp confirmed delivery to recipient's device
        ('READ', 'Read'),                  # Recipient read the message
        ('FAILED', 'Failed'),              # API rejected message or delivery failed
        ('RECEIVED', 'Received (Incoming)'), # Incoming message stored
    ]
    # Use WhatsApp Message ID as primary key for idempotency
    message_id = models.CharField(
        max_length=100,
        unique=True,
        primary_key=True,
        help_text="WhatsApp Message ID (wamid) provided by the API."
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE, # Delete messages if contact is deleted
        related_name='messages',
        help_text="The contact associated with this message."
    )
    direction = models.CharField(
        max_length=3,
        choices=MESSAGE_DIRECTION_CHOICES,
        help_text="Was the message sent from or received by the nursery?"
    )
    status = models.CharField(
        max_length=10,
        choices=MESSAGE_STATUS_CHOICES,
        default='RECEIVED', # Default for incoming, will be updated for outgoing
        db_index=True,
        help_text="Delivery status of the message (updated via webhooks for outgoing)."
    )
    message_type = models.CharField(
        max_length=20,
        default='text',
        help_text="Type of message (e.g., text, image, template, location)."
    )
    text_content = models.TextField(
        blank=True,
        null=True,
        help_text="Text content of the message (or description for non-text types)."
    )
    media_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL of the media file (if applicable, might need separate download)."
    )
    template_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Name of the template used (if applicable)."
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Timestamp when the message was processed/sent by this system."
    )
    whatsapp_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Original timestamp provided by WhatsApp (UTC)."
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Details if the message failed to send or process."
    )

    # ***** Integration Point *****
    # Link to relevant nursery models if a message relates to something specific
    # Example: Assuming you have an 'orders' app with an 'Order' model
    # from orders.models import Order # Handle potential circular imports
    # related_order = models.ForeignKey(
    #    Order,
    #    on_delete=models.SET_NULL, # Keep message even if order is deleted
    #    null=True,
    #    blank=True,
    #    related_name='whatsapp_messages',
    #    help_text="Link to a specific nursery order, if relevant."
    # )

    def __str__(self):
        return f"{self.get_direction_display()} message {self.message_id} ({self.contact.wa_id})"
class MarketingTemplate(models.Model):
    """Stores details about approved WhatsApp message templates relevant to the nursery."""
    name = models.CharField(
        max_length=100,
        help_text="Exact template name from WhatsApp Business Manager (case-sensitive)."
    )
    language = models.CharField(
        max_length=10,
        default='en',
        help_text="Language code of the template (e.g., 'en', 'en_US', 'hi')."
    )
    category = models.CharField(
        max_length=50,
        help_text="Category assigned by Meta (e.g., MARKETING, UTILITY, AUTHENTICATION)."
    )
    # Store the component structure needed for sending messages
    components = models.JSONField(
        help_text="Structure of the template (header, body, footer, buttons) obtained from API sync."
    )
    last_synced = models.DateTimeField(
        auto_now=True,
        help_text="When this template information was last updated from the API."
    )

    def __str__(self):
        return f"{self.name} ({self.language})"

    class Meta:
        unique_together = ('name', 'language') # A template is unique by name and language
        verbose_name = "WhatsApp Template"
        verbose_name_plural = "WhatsApp Templates"
        ordering = ['name', 'language']


class MarketingCampaign(models.Model):
    """Represents a bulk messaging campaign for the nursery (e.g., promotions, new arrivals)."""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),  # Campaign created, contacts being added
        ('SCHEDULED', 'Scheduled'),  # Ready to send at a specific time
        ('SENDING', 'Sending'),  # Celery task is actively processing recipients
        ('COMPLETED', 'Completed'),  # All messages processed (might include failures)
        ('FAILED', 'Failed'),  # Major issue prevented sending (e.g., API error, task crash)
        ('CANCELLED', 'Cancelled'),  # Manually cancelled before sending
    ]
    
    name = models.CharField(
        max_length=150,
        help_text="Internal name for this campaign (e.g., 'Spring Sale 2025')."
    )
    template = models.ForeignKey(
        MarketingTemplate,
        on_delete=models.PROTECT, # Prevent deleting a template used in campaigns
        related_name='campaigns',
        help_text="The approved WhatsApp template to use for this campaign."
    )
    scheduled_time = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Scheduled Time',
        help_text="If set, the campaign will start sending at this time (uses Celery Beat or scheduler)."
    )
    is_sent = models.BooleanField(
        default=False,
        help_text="If set, the campaign will start sending at this time (uses Celery Beat or scheduler)."
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True,
        help_text="Current status of the campaign."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )
    started_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Started At", help_text="Timestamp when sending actually began.")
    completed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Completed At", help_text="Timestamp when all messages were processed.")

    # Optional: Track who created the campaign
    # created_by = models.ForeignKey(
    #    settings.AUTH_USER_MODEL,
    #    on_delete=models.SET_NULL, # Keep campaign even if user is deleted
    #    null=True,
    #    blank=True,
    #    related_name='created_campaigns'
    # )

    def __str__(self):
        return f"Campaign: {self.name} ({self.get_status_display()})"

    class Meta:
        verbose_name = "Marketing Campaign",
        verbose_name_plural = "Marketing Campaigns",
        ordering = ['-created_at'],


class CampaignContact(models.Model): 
    """Associates contacts with a campaign and tracks individual message status and variables."""
    STATUS_CHOICES = ChatMessage.MESSAGE_STATUS_CHOICES # Reuse status choices from ChatMessage for consistency
    campaign = models.ForeignKey(
        MarketingCampaign,
        on_delete=models.CASCADE, # Delete recipient entries if campaign is deleted
        related_name='recipients'
    )
    contact = models.ForeignKey(
        Contact, 
        on_delete=models.CASCADE, # Or PROTECT if you want to prevent contact deletion if part of campaign
        related_name='marketing_messages'
    )
    # Store dynamic variable values for the template for this specific contact
    template_variables = models.JSONField(
        blank=True,
        null=True,
        help_text='Variables for the template, e.g., {"1": "Customer Name", "2": "Discount Code"}'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING', # Initial status before sending attempt
        db_index=True,
        help_text="Delivery status of the message sent to this contact for this campaign."
    )
    # Store the WAMID of the message sent for this campaign contact
    message_id = models.CharField(
        max_length=100,
        blank=True, 
        null=True,
        db_index=True, # Index for faster lookups based on status webhooks
        help_text="WhatsApp Message ID (wamid) of the sent message."
    )
    sent_time = models.DateTimeField(null=True, blank=True, help_text="Timestamp when the message was sent via API.")
    error_message = models.TextField(blank=True, null=True, help_text="Error details if sending failed for this contact.")

    class Meta:
        unique_together = ('campaign', 'contact') # Ensure a contact is only added once per campaign
        verbose_name = "Campaign Recipient"
        verbose_name_plural = "Campaign Recipients"
        ordering = ['campaign', 'contact__wa_id']

# --- Bots & Automation (Optional) ---
class BotResponse(models.Model):
    """
    Stores predefined answers for common nursery questions.
    """
    question = models.TextField(
        verbose_name="Question",
        help_text="The question or phrase that triggers this response.",
    )
    answer = models.TextField(
        verbose_name="Answer",
        help_text="The message text to send back as an answer.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active",
        help_text="Whether this bot response is currently enabled.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    def __str__(self):
        return self.question
    class Meta:
        verbose_name = "Bot Response"
        verbose_name_plural = "Bot Responses"
        ordering = ['trigger_phrase']

class AutoReply(models.Model):
    """Settings for the single auto-reply message sent when staff are unavailable."""
    keywords = models.TextField(
        help_text="Keywords that trigger this auto-reply (comma-separated)."
    )
    response = models.TextField(
        help_text="The message sent automatically in response to matching keywords."
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Is Active",
        help_text="Enable or disable the auto-reply feature."
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")
    is_enable = models.BooleanField(
        help_text="Enable or disable the auto-reply feature."
    )
    # Optional: Add fields for time-based rules (e.g., start_time, end_time, active_days)

    def __str__(self):
        return "Auto-Reply Settings"


    class Meta:
        verbose_name = "Auto Reply Setting"
        verbose_name_plural = "Auto Reply Settings"
        # Add constraint to ensure only one instance exists
        # constraints = [
        #     models.UniqueConstraint(fields=['id'], condition=models.Q(id=1), name='singleton_autoreply_constraint')
        # ]
