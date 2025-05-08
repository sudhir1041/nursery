from django.contrib import admin
from django.db.models import Count # Import Count for annotation
from django.utils import timezone # Import timezone for actions
from .models import (
    WhatsAppSettings, Contact, ChatMessage, MarketingTemplate,
    MarketingCampaign, CampaignContact, BotResponse, AutoReply
)

# --- Inline Admin for related models ---

class ChatMessageInline(admin.TabularInline):
    """Inline display for messages within the Contact admin page."""
    model = ChatMessage
    fields = ('timestamp', 'direction', 'message_type', 'text_content', 'status') # Fields to display inline
    readonly_fields = ('timestamp', 'direction', 'message_type', 'text_content', 'status', 'message_id') # Make them read-only
    extra = 0 # Don't show extra blank forms
    ordering = ('-timestamp',) # Show newest messages first
    can_delete = False # Usually don't want to delete messages from here
    show_change_link = True # Link to the full ChatMessage admin
    verbose_name_plural = "Recent Messages"

class CampaignContactInline(admin.TabularInline):
    """Inline display for recipients within the MarketingCampaign admin page."""
    model = CampaignContact
    fields = ('contact_link', 'status', 'sent_time', 'message_id') # Use contact_link method
    readonly_fields = ('contact_link', 'status', 'sent_time', 'message_id', 'error_message') # Make fields read-only
    extra = 0
    # show_change_link = True # Link to CampaignContact admin if needed, often not necessary inline
    can_delete = False # Prevent deleting recipients from campaign view directly
    verbose_name_plural = "Campaign Recipients"

    @admin.display(description='Contact')
    def contact_link(self, obj):
        """Create a link to the related Contact admin page."""
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.contact:
            link = reverse("admin:whatsapp_app_contact_change", args=[obj.contact.pk])
            # Display name or wa_id
            display_text = obj.contact.name or obj.contact.wa_id
            return format_html('<a href="{}">{}</a>', link, display_text)
        return "-"

    # Improve performance for large campaigns by limiting initial display
    # max_num = 20 # Show only first 20 recipients inline initially

# --- Main ModelAdmin configurations ---

@admin.register(WhatsAppSettings)
class WhatsAppSettingsAdmin(admin.ModelAdmin):
    """Admin configuration for WhatsApp Settings."""
    list_display = ('account_name', 'phone_number_id', 'whatsapp_business_account_id', 'is_live_mode', 'last_validated')
    list_filter = ('is_live_mode',)
    search_fields = ('account_name', 'phone_number_id', 'whatsapp_business_account_id')
    # Prevent adding more than one settings object if it's intended as a singleton
    def has_add_permission(self, request):
        # Allow add only if no settings exist yet with the default name (or adjust logic)
        return not WhatsAppSettings.objects.filter(account_name="NurseryProjectDefault").exists()

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    """Admin configuration for WhatsApp Contacts."""
    list_display = ('wa_id', 'name', 'created_at', 'updated_at') # Add linked customer/user field if exists
    search_fields = ('wa_id', 'name') # Add linked customer/user field if exists
    list_filter = ('created_at',)
    readonly_fields = ('wa_id', 'created_at', 'updated_at') # wa_id is PK, shouldn't be changed
    inlines = [ChatMessageInline] # Show recent messages directly on contact page
    list_per_page = 25

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """Admin configuration for individual Chat Messages."""
    list_display = ('message_id', 'contact_link', 'direction', 'message_type', 'status', 'timestamp')
    list_filter = ('direction', 'status', 'message_type', 'timestamp')
    search_fields = ('message_id', 'contact__wa_id', 'contact__name', 'text_content', 'template_name')
    # Make most fields read-only as they come from WhatsApp
    readonly_fields = ('message_id', 'contact', 'direction', 'message_type', 'text_content',
                       'media_url', 'template_name', 'timestamp', 'whatsapp_timestamp',
                       'status', 'error_message') # Status should only change via webhook
    date_hierarchy = 'timestamp' # Allow easy date filtering
    list_per_page = 50

    @admin.display(description='Contact', ordering='contact__name') # Add ordering
    def contact_link(self, obj):
        """Create a link to the related Contact admin page."""
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.contact:
            link = reverse("admin:whatsapp_app_contact_change", args=[obj.contact.pk])
            display_text = obj.contact.name or obj.contact.wa_id
            return format_html('<a href="{}">{}</a>', link, display_text)
        return "-"

    # Prevent manual creation/deletion of messages
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False # Messages should generally be immutable logs

@admin.register(MarketingTemplate)
class MarketingTemplateAdmin(admin.ModelAdmin):
    """Admin configuration for WhatsApp Message Templates."""
    list_display = ('name', 'language', 'category', 'last_synced')
    list_filter = ('category', 'language')
    search_fields = ('name',)
    # Templates are synced from API, make fields read-only
    readonly_fields = ('name', 'language', 'category', 'components', 'last_synced')

    # Prevent manual creation/deletion - should be synced from API
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        # Allow deletion if needed, but usually templates are managed via Meta
        return False

@admin.register(MarketingCampaign)
class MarketingCampaignAdmin(admin.ModelAdmin):
    """Admin configuration for Marketing Campaigns."""
    list_display = ('name', 'template', 'status', 'recipient_count', 'scheduled_time', 'started_at', 'completed_at')
    list_filter = ('status', 'created_at', 'scheduled_time', 'template')
    search_fields = ('name', 'template__name')
    # Make fields managed by the system read-only in admin
    # *** CORRECTED: Removed 'created_by' as it's not in the model ***
    readonly_fields = ('status', 'started_at', 'completed_at', 'created_at')
    list_per_page = 30
    inlines = [CampaignContactInline]
    actions = ['send_draft_campaigns_now'] # Example action
    date_hierarchy = 'created_at'

    @admin.display(description='Recipients', ordering='recipient_count') # Add ordering
    def recipient_count(self, obj):
        """Calculate recipient count. Annotated in get_queryset for efficiency."""
        # This value comes from the annotation in get_queryset
        return obj.recipient_count if hasattr(obj, 'recipient_count') else 'N/A'

    # Annotate recipient count in queryset for efficiency
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(recipient_count=Count('recipients'))
        return queryset

    @admin.action(description='Start sending selected DRAFT campaigns now')
    def send_draft_campaigns_now(self, request, queryset):
        """Action to immediately trigger sending for selected draft campaigns."""
        # Import task locally to avoid potential startup issues if Celery isn't ready
        try:
            from .tasks import send_bulk_campaign_messages_task
            celery_enabled = True
        except ImportError:
            celery_enabled = False

        if not celery_enabled:
            self.message_user(request, "Celery is not configured or running. Cannot send campaigns.", level='error')
            return

        started_count = 0
        skipped_count = 0
        no_recipient_count = 0
        for campaign in queryset:
            if campaign.status == 'DRAFT':
                # Re-check recipient count just before sending
                if campaign.recipients.exists():
                    campaign.status = 'SENDING'
                    campaign.started_at = timezone.now()
                    campaign.scheduled_time = None
                    campaign.save(update_fields=['status', 'started_at', 'scheduled_time'])
                    send_bulk_campaign_messages_task.delay(campaign.id)
                    started_count += 1
                else:
                    no_recipient_count +=1
            else:
                skipped_count += 1

        if started_count:
            self.message_user(request, f"Started sending {started_count} campaigns.", level='success')
        if skipped_count:
            self.message_user(request, f"Skipped {skipped_count} campaigns (not in Draft status).", level='warning')
        if no_recipient_count:
             self.message_user(request, f"Skipped {no_recipient_count} draft campaigns (no recipients added).", level='warning')


@admin.register(CampaignContact)
class CampaignContactAdmin(admin.ModelAdmin):
    """Admin configuration for individual campaign recipients (mostly read-only)."""
    list_display = ('campaign', 'contact_link', 'status', 'sent_time', 'message_id')
    list_filter = ('status', 'campaign')
    search_fields = ('contact__wa_id', 'contact__name', 'campaign__name', 'message_id')
    # Make fields read-only as they are managed by the campaign sending process
    readonly_fields = ('campaign', 'contact', 'template_variables', 'status',
                       'message_id', 'sent_time', 'error_message')
    list_per_page = 50

    @admin.display(description='Contact', ordering='contact__name') # Add ordering
    def contact_link(self, obj):
        """Create a link to the related Contact admin page."""
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.contact:
            link = reverse("admin:whatsapp_app_contact_change", args=[obj.contact.pk])
            display_text = obj.contact.name or obj.contact.wa_id
            return format_html('<a href="{}">{}</a>', link, display_text)
        return "-"

    # Usually don't want users adding/changing these directly
    def has_add_permission(self, request):
        return False
    # Prevent changes unless specifically needed
    def has_change_permission(self, request, obj=None):
         return False # Make it strictly read-only in admin
    def has_delete_permission(self, request, obj=None):
         return False # Don't allow deleting individual recipient logs

@admin.register(BotResponse)
class BotResponseAdmin(admin.ModelAdmin):
    """Admin configuration for Chatbot Responses."""
    list_display = ('trigger_phrase', 'response_preview', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('trigger_phrase', 'response_text')
    list_editable = ('is_active',) # Allow toggling active status directly in list view
    list_per_page = 25

    @admin.display(description='Response Preview')
    def response_preview(self, obj):
        """Show a truncated preview of the response text."""
        from django.utils.text import Truncator
        return Truncator(obj.response_text).chars(80)

@admin.register(AutoReply)
class AutoReplyAdmin(admin.ModelAdmin):
    """Admin configuration for Auto-Reply Settings."""
    list_display = ('__str__', 'is_active', 'message_preview') # Use __str__ for identification

    @admin.display(description='Message Preview')
    def message_preview(self, obj):
        from django.utils.text import Truncator
        return Truncator(obj.message_text).chars(100)

    # Prevent adding more than one settings object if it's intended as a singleton
    def has_add_permission(self, request):
        return not AutoReply.objects.exists()
    def has_delete_permission(self, request, obj=None):
         return False # Don't allow deletion, just deactivation/editing
