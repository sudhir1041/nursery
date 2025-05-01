# whatsapp/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q, Max
from django.contrib.auth.decorators import login_required, user_passes_test # Or custom permission decorators
from django.contrib import messages # Use Django's messaging framework
from django.conf import settings as django_settings # For project level settings if needed
import json
import csv
import io
import logging
from django.urls import reverse

import uuid # For webhook token generation if needed

# Models from this app
from .models import (
    Contact, ChatMessage, WhatsAppSettings, BotResponse, AutoReply,
    MarketingTemplate, MarketingCampaign, CampaignContact
)
# Forms from this app
from .forms import (
    WhatsAppSettingsForm, ManualMessageForm, MarketingCampaignForm,
    ContactUploadForm , BotResponseForm,AutoReplySettingsForm# Add BotResponseForm, AutoReplyForm if using dedicated views
)
# Utilities from this app
from .utils import (
    send_whatsapp_message, parse_incoming_whatsapp_message,
    fetch_whatsapp_templates_from_api, get_active_whatsapp_settings
    # Add verify_whatsapp_signature if implementing webhook security
)
# Celery tasks (assuming they are defined in tasks.py)
# Import tasks only if Celery is configured and used
try:
    from .tasks import send_bulk_campaign_messages_task
    # from .tasks import process_uploaded_contacts_task # If using background CSV processing
    CELERY_ENABLED = True
except ImportError:
    CELERY_ENABLED = False
    # Define dummy task functions if Celery is not installed/enabled to avoid NameErrors
    def send_bulk_campaign_messages_task(*args, **kwargs):
        logger.error("Celery not configured. Cannot run background tasks.")
        # Optionally raise an error or return a failure indicator
        raise NotImplementedError("Celery is not enabled or tasks are not defined.")


logger = logging.getLogger(__name__) # Use logger defined in settings.py

# --- Helper: Check if user is admin/staff ---
# Replace this with your project's actual permission checking logic
def is_staff_user(user):
    """Checks if the user is authenticated and has staff privileges."""
    return user.is_authenticated and user.is_staff

# --- Dashboard ---
@user_passes_test(is_staff_user) # Example: Restrict to staff users
def dashboard(request):
    """Displays overview statistics related to WhatsApp integration."""
    today = timezone.now().date()
    stats = {} # Initialize stats dictionary

    try:
        # Query optimization: Use select_related/prefetch_related where applicable if needed later
        stats['total_contacts'] = Contact.objects.count()
        stats['active_chats_count'] = Contact.objects.filter(messages__isnull=False).distinct().count()

        messages_today_qs = ChatMessage.objects.filter(timestamp__date=today)
        stats['messages_today'] = messages_today_qs.count()
        stats['incoming_today'] = messages_today_qs.filter(direction='IN').count()
        stats['outgoing_today'] = messages_today_qs.filter(direction='OUT').count()

        # Basic delivery stats (can be slow on large datasets without optimization)
        # Consider calculating these periodically or using annotations for better performance
        outgoing_messages = ChatMessage.objects.filter(direction='OUT')
        total_outgoing = outgoing_messages.count()
        delivered_count = outgoing_messages.filter(status__in=['DELIVERED', 'READ']).count()
        failed_count = outgoing_messages.filter(status='FAILED').count()
        stats['success_rate'] = (delivered_count / total_outgoing * 100) if total_outgoing > 0 else 0
        stats['failed_count'] = failed_count

        # Recent Campaigns (Example)
        stats['recent_campaigns'] = MarketingCampaign.objects.select_related('template').order_by('-created_at')[:5]

    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        messages.error(request, "Could not load all dashboard statistics.")
        # Provide default values to prevent template errors
        stats.setdefault('total_contacts', 0)
        stats.setdefault('active_chats_count', 0)
        stats.setdefault('messages_today', 0)
        stats.setdefault('incoming_today', 0)
        stats.setdefault('outgoing_today', 0)
        stats.setdefault('success_rate', 0)
        stats.setdefault('failed_count', 0)
        stats.setdefault('recent_campaigns', [])

    context = stats # Pass the whole dictionary
    return render(request, 'whatsapp/dashboard.html', context)

# --- Settings ---
@user_passes_test(is_staff_user)
def whatsapp_settings_view(request):
    """Manages WhatsApp Cloud API settings."""
    settings_name = "NurseryProjectDefault" # Define a default name or get from config
    # Use get_or_create with the specific name
    settings_instance, created = WhatsAppSettings.objects.get_or_create(
        account_name=settings_name,
        defaults={
            # Generate a new verify token only if creating the record
            'webhook_verify_token': str(uuid.uuid4())
        }
    )

    if request.method == 'POST':
        form = WhatsAppSettingsForm(request.POST, instance=settings_instance)
        if form.is_valid():
            try:
                # Save form without committing to get settings object
                # This isn't strictly necessary if not modifying before final save,
                # but kept here based on user's code structure.
                settings = form.save(commit=False)

                # Optional validation logic (ensure validate_api_credentials exists if uncommented)
                # if validate_api_credentials(settings):
                #     settings.last_validated = timezone.now()
                # else:
                #     settings.last_validated = None
                #     messages.warning(request, "Could not validate credentials with WhatsApp API.")

                # Save settings with any additional fields
                settings.save()

                # Save many-to-many relationships if any (usually not needed for settings)
                # form.save_m2m() # Uncomment if your settings form has M2M fields

                messages.success(request, 'WhatsApp settings updated successfully.')

                # Remind user about webhook updates if URL/token changed
                if form.has_changed() and any(field in form.changed_data for field in ['webhook_url', 'webhook_verify_token']):
                    messages.info(request, "Remember to update the Webhook URL and Verify Token in the Meta Developer Portal for your WhatsApp App.")

                # *** CORRECTED NAMESPACE IN REDIRECT ***
                # Ensure 'settings' is the correct URL name in whatsapp_app/urls.py
                return redirect('whatsapp_app:settings')

            except Exception as e:
                logger.exception(f"Error saving WhatsApp settings: {e}") # Use logger.exception
                messages.error(request, f"Failed to save settings: {e}")

        else:
            # Improved error message display for invalid form
            error_list = []
            for field, errors in form.errors.items():
                 # Use field label if available, otherwise fallback to field name
                field_label = form.fields.get(field).label if form.fields.get(field) else field.replace('_', ' ').title()
                error_list.append(f"{field_label}: {'; '.join(errors)}")
            messages.error(request, f"Please correct the errors: {'. '.join(error_list)}")
            # No redirect here, re-render the form with errors below
    else:
        form = WhatsAppSettingsForm(instance=settings_instance)

    # Build the full webhook URL to display in the template
    full_webhook_url = None
    # Check settings_instance again as it might be None if get_or_create fails (unlikely but safe)
    if settings_instance:
        try:
            # Prefer using reverse with the correct namespace for the webhook handler view
            # Ensure 'webhook_handler' is the name of your webhook view in urls.py
            webhook_path = reverse('whatsapp_app:webhook_handler')
            full_webhook_url = request.build_absolute_uri(webhook_path)
        except Exception as e:
            logger.warning(f"Could not reverse URL for 'whatsapp_app:webhook_handler'. Check urls.py. Error: {e}")
            # Fallback or leave as None if reverse fails

    context = {
        'form': form,
        'settings': settings_instance,
        'full_webhook_url': full_webhook_url
    }
    # Ensure this template path is correct
    return render(request, 'whatsapp/settings_form.html', context)




# --- Webhook Handler ---
@csrf_exempt # WhatsApp doesn't send CSRF tokens
def whatsapp_webhook(request):
    """Handles incoming notifications (messages, status updates) from WhatsApp."""
    # 1. Verify Signature (Highly Recommended for Production)
    # app_secret = getattr(django_settings, 'WA_APP_SECRET', None) # Store App Secret securely in settings or .env
    # if app_secret:
    #    signature = request.headers.get('X-Hub-Signature-256')
    #    if not verify_whatsapp_signature(request.body, signature, app_secret):
    #        logger.warning("Invalid webhook signature received.")
    #        return HttpResponseForbidden("Invalid signature.")
    # else:
    #    logger.warning("WA_APP_SECRET not configured. Skipping webhook signature verification (INSECURE).")


    # 2. Handle Verification Request (GET) - Used only once during webhook setup
    if request.method == 'GET':
        verify_token_param = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        try:
            # Fetch the *expected* token from settings
            settings = get_active_whatsapp_settings()
            expected_token = settings.webhook_verify_token
            if verify_token_param == expected_token and challenge:
                logger.info(f"Webhook verification successful for token: {expected_token}")
                return HttpResponse(challenge, status=200)
            else:
                logger.warning(f"Webhook verification failed. Received token: '{verify_token_param}', Expected: '{expected_token}'")
                return HttpResponseForbidden("Verification token mismatch.")
        except WhatsAppSettings.DoesNotExist:
             logger.error("Webhook verification failed: WhatsAppSettings not found.")
             return HttpResponseForbidden("Configuration error: Settings not found.")
        except ValueError as e: # Catches config errors from get_active_whatsapp_settings
             logger.error(f"Webhook verification failed: Configuration error - {e}")
             return HttpResponseForbidden(f"Configuration error: {e}")
        except Exception as e:
            logger.error(f"Error during webhook GET verification: {e}")
            return HttpResponseForbidden("Internal server error during verification.")

    # 3. Handle Incoming Notifications (POST)
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            # Process the payload using the utility function from utils.py
            processed_data = parse_incoming_whatsapp_message(payload)

            # --- Trigger Bot/Auto-Reply Logic (if message received) ---
            if processed_data and processed_data.get('type') == 'incoming_message':
                message_obj = processed_data.get('message_object')
                if message_obj:
                    # Call the helper function (defined below this view)
                    handle_bot_or_autoreply(message_obj)

            # Acknowledge receipt to WhatsApp IMMEDIATELY (required)
            return HttpResponse(status=200)

        except json.JSONDecodeError:
            logger.error("Invalid JSON received in webhook POST request.")
            return HttpResponseBadRequest("Invalid JSON.")
        except Exception as e:
            # Log the error thoroughly but still return 200 OK to WhatsApp
            # to prevent Meta from resending the same faulty notification repeatedly.
            logger.exception(f"Error processing webhook POST payload: {e}")
            # Acknowledge receipt even if processing failed internally.
            return HttpResponse(status=200)

    # Method Not Allowed for other HTTP verbs (PUT, DELETE, etc.)
    logger.warning(f"Received webhook request with unsupported method: {request.method}")
    return HttpResponse(status=405)

# --- Helper Function for Bots/Auto-Replies (Called by Webhook) ---
def handle_bot_or_autoreply(incoming_message: ChatMessage):
    """Checks and sends bot responses or auto-replies based on incoming message."""
    # Only process text messages for keyword triggers/replies
    if not incoming_message or not incoming_message.text_content or incoming_message.direction != 'IN':
        return

    contact = incoming_message.contact
    message_text_lower = incoming_message.text_content.lower().strip()
    bot_responded = False

    # 1. Check for Bot Triggers (Exact Match, Case-Insensitive)
    try:
        # Fetch active bot responses matching the trigger phrase
        bot_response = BotResponse.objects.filter(is_active=True, trigger_phrase__iexact=message_text_lower).first()
        if bot_response:
            # Simple loop prevention: Check if the last outgoing message wasn't this exact bot response
            last_out_msg = ChatMessage.objects.filter(contact=contact, direction='OUT').order_by('-timestamp').first()
            if not last_out_msg or last_out_msg.text_content != bot_response.response_text:
                send_whatsapp_message(
                    recipient_wa_id=contact.wa_id,
                    message_type='text',
                    text_content=bot_response.response_text
                )
                logger.info(f"Sent bot response for trigger '{bot_response.trigger_phrase}' to {contact.wa_id}")
                bot_responded = True # Mark that bot handled it
            else:
                 logger.info(f"Skipping bot response for '{bot_response.trigger_phrase}' to {contact.wa_id} to prevent potential loop.")
                 bot_responded = True # Still consider it handled to prevent auto-reply

    except Exception as e:
        logger.error(f"Error checking/sending bot response for {contact.wa_id}: {e}")

    # 2. Check for Auto-Reply (Only if no bot response was sent)
    if not bot_responded:
        # Implement your logic for 'agent availability' here.
        # This could check business hours, staff online status (if tracked), etc.
        # For this example, we'll just check if the AutoReply setting is active.
        agent_available = False # <<<--- Replace with your actual availability logic --->>>
        # Example: Check current time against business hours stored elsewhere?

        if not agent_available:
            try:
                auto_reply_settings = AutoReply.objects.filter(is_active=True).first()
                if auto_reply_settings:
                    # Simple loop prevention: Check if the last outgoing message wasn't this exact auto-reply
                    last_out_msg = ChatMessage.objects.filter(contact=contact, direction='OUT').order_by('-timestamp').first()
                    if not last_out_msg or last_out_msg.text_content != auto_reply_settings.message_text:
                        send_whatsapp_message(
                            recipient_wa_id=contact.wa_id,
                            message_type='text',
                            text_content=auto_reply_settings.message_text
                        )
                        logger.info(f"Sent auto-reply to {contact.wa_id}")
                    else:
                        logger.info(f"Skipping auto-reply to {contact.wa_id} to prevent potential loop.")

            except Exception as e:
                logger.error(f"Error checking/sending auto-reply for {contact.wa_id}: {e}")


# --- Chat List & Detail ---
@user_passes_test(is_staff_user)
def chat_list(request):
    """Displays a list of contacts with recent chat activity."""
    search_query = request.GET.get('q', '').strip()

    # Get contacts, ordered by the timestamp of their last message
    # Annotate with last message time for ordering
    contacts_with_messages = Contact.objects.annotate(
        last_message_time=Max('messages__timestamp')
    ).filter(last_message_time__isnull=False) # Only contacts with messages

    # Apply search filter if query exists
    if search_query:
        contacts_with_messages = contacts_with_messages.filter(
            Q(name__icontains=search_query) | Q(wa_id__icontains=search_query)
            # Add search on linked customer/user fields if applicable
            # | Q(customer__name__icontains=search_query)
        )

    # Order by the annotated last message time
    contacts = contacts_with_messages.order_by('-last_message_time')

    # Note: Getting last message preview here is inefficient.
    # It's better to display this in the template by accessing messages.last
    # or store it on the Contact model via signals/tasks if performance is critical.

    context = {
        'contacts': contacts,
        'search_query': search_query,
    }
    return render(request, 'whatsapp/chat_list.html', context)

@user_passes_test(is_staff_user)
def chat_detail(request, wa_id):
    """Displays the message history for a specific contact and allows sending messages."""
    contact = get_object_or_404(Contact, wa_id=wa_id)
    # Fetch messages ordered by timestamp for display
    messages_qs = ChatMessage.objects.filter(contact=contact).order_by('timestamp')
    form = ManualMessageForm() # Form for sending new message

    # Optional: Mark incoming messages as 'READ' when viewed by staff
    # Be careful with bulk updates on large conversations; consider background tasks or JS triggers
    # messages_qs.filter(direction='IN', status='RECEIVED').update(status='READ')

    # Get the timestamp of the very last message (or current time if none) for AJAX polling
    last_msg = messages_qs.last()
    last_message_timestamp_iso = last_msg.timestamp.isoformat() if last_msg else timezone.now().isoformat()

    context = {
        'contact': contact,
        'messages': messages_qs,
        'form': form,
        'last_message_timestamp': last_message_timestamp_iso,
    }
    return render(request, 'whatsapp/chat_detail.html', context)

# --- AJAX Endpoints for Chat ---
@user_passes_test(is_staff_user)
@require_POST
# Ensure CSRF protection is properly handled in your AJAX setup (e.g., sending X-CSRFToken header)
def send_manual_message_ajax(request, wa_id):
    """AJAX endpoint to send a manual message."""
    contact = get_object_or_404(Contact, wa_id=wa_id)
    form = ManualMessageForm(request.POST)
    if form.is_valid():
        message_text = form.cleaned_data['text_content']
        try:
            # Call the utility function to send via API and log the ChatMessage
            message_obj = send_whatsapp_message(
                recipient_wa_id=contact.wa_id,
                message_type='text',
                text_content=message_text
                # Pass other relevant IDs if needed for logging context, e.g.:
                # related_order_id=request.POST.get('order_id')
            )
            if message_obj:
                 # Return details of the sent message for immediate UI update (optional)
                 return JsonResponse({
                     'status': 'success',
                     'message': {
                         'message_id': message_obj.message_id,
                         'text_content': message_obj.text_content,
                         'timestamp': message_obj.timestamp.isoformat(), # Use system timestamp for immediate display
                         'direction': 'OUT',
                         'status': message_obj.status, # Should be 'SENT' or 'PENDING' initially
                         'message_type': message_obj.message_type,
                         'template_name': message_obj.template_name,
                         'media_url': message_obj.media_url,
                     }
                 })
            else:
                # Error occurred within send_whatsapp_message (already logged there)
                return JsonResponse({'status': 'error', 'message': 'Failed to initiate sending message via API.'}, status=500)
        except Exception as e:
            logger.error(f"Error in send_manual_message_ajax view for {wa_id}: {e}")
            return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred.'}, status=500)
    else:
        # Form validation failed
        logger.warning(f"Manual message form validation failed for {wa_id}: {form.errors.as_json()}")
        return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

@user_passes_test(is_staff_user)
@require_GET
def get_latest_messages_ajax(request):
    """AJAX endpoint for polling new messages for a specific chat."""
    wa_id = request.GET.get('wa_id')
    last_timestamp_str = request.GET.get('last_timestamp') # ISO format timestamp from client

    if not wa_id or not last_timestamp_str:
        return JsonResponse({'status': 'error', 'message': 'Missing required parameters (wa_id, last_timestamp)'}, status=400)

    try:
        contact = Contact.objects.get(wa_id=wa_id)
        # Parse the timestamp provided by the client (last known message timestamp)
        last_timestamp = parse_datetime(last_timestamp_str)
        if not last_timestamp:
             logger.warning(f"Invalid timestamp format received from client: {last_timestamp_str}")
             return JsonResponse({'status': 'error', 'message': 'Invalid timestamp format'}, status=400)
         # Ensure it's timezone-aware for comparison with database timestamps
        if timezone.is_naive(last_timestamp):
             # Assume client sent in default timezone, make it aware
             last_timestamp = timezone.make_aware(last_timestamp, timezone.get_default_timezone())

        # Fetch messages strictly newer than the last one the client reported
        # Order by timestamp to ensure correct display order
        new_messages_qs = ChatMessage.objects.filter(
            contact=contact,
            timestamp__gt=last_timestamp # Use system timestamp for reliable ordering
        ).order_by('timestamp')

        # Select only needed fields for efficiency to send back as JSON
        new_messages_data = list(new_messages_qs.values(
            'message_id', 'text_content', 'timestamp', 'direction', 'status',
            'media_url', 'message_type', 'template_name'
        ))

        # Optional: Mark fetched incoming messages as read here?
        # incoming_to_mark_read = new_messages_qs.filter(direction='IN', status='RECEIVED')
        # if incoming_to_mark_read.exists():
        #     incoming_to_mark_read.update(status='READ')
        #     logger.info(f"Marked {incoming_to_mark_read.count()} incoming messages as READ for {wa_id}")

        # Determine the timestamp for the *next* poll
        # Use the timestamp of the latest message found, or the previous timestamp if none found
        latest_ts_in_response = new_messages_qs.last().timestamp if new_messages_qs.exists() else last_timestamp
        next_poll_timestamp_iso = latest_ts_in_response.isoformat()

        return JsonResponse({
            'status': 'success',
            'new_messages': new_messages_data,
            'next_poll_timestamp': next_poll_timestamp_iso, # Tell client the new 'last_timestamp' to use
            # 'updated_statuses': [] # Optional: Add logic to detect status changes for older messages if needed
        })
    except Contact.DoesNotExist:
        logger.warning(f"Contact not found during latest messages poll: {wa_id}")
        return JsonResponse({'status': 'error', 'message': 'Contact not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching latest messages for {wa_id}: {e}")
        return JsonResponse({'status': 'error', 'message': 'Server error fetching messages'}, status=500)


# --- Marketing Views ---
@user_passes_test(is_staff_user)
def campaign_list(request):
    """Lists all marketing campaigns."""
    # Optimize by selecting related template name
    campaigns = MarketingCampaign.objects.select_related('template').order_by('-created_at')
    context = {'campaigns': campaigns}
    # Corrected template path assumption
    return render(request, 'whatsapp/marketing/campaign_list.html', context)


# --- Campaign Detail View ---
@user_passes_test(is_staff_user)
def campaign_detail(request, pk):
    """Shows details and recipients of a specific campaign."""
    # Fetch campaign with related template
    campaign = get_object_or_404(MarketingCampaign.objects.select_related('template'), pk=pk)
    # Fetch recipients with related contact info
    # Ensure CampaignContact model and its relation to Contact are correctly defined
    recipients = CampaignContact.objects.filter(campaign=campaign).select_related('contact').order_by('contact__wa_id')

    # Calculate summary stats efficiently using aggregation
    stats = recipients.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='PENDING')),
        sent=Count('id', filter=Q(status='SENT')),
        delivered=Count('id', filter=Q(status='DELIVERED')),
        read=Count('id', filter=Q(status='READ')),
        failed=Count('id', filter=Q(status='FAILED')),
    )
    # Calculate percentages safely
    stats['sent_pct'] = 0
    stats['delivered_pct'] = 0
    stats['read_pct'] = 0
    stats['failed_pct'] = 0
    if stats['total'] > 0:
        # Calculate total processed (non-pending) for percentage base if preferred
        processed_total = stats['total'] - stats['pending']
        base = processed_total if processed_total > 0 else 1 # Avoid division by zero

        # Calculate based on total recipients initiated
        stats['sent_pct'] = round((stats['sent'] + stats['delivered'] + stats['read'] + stats['failed']) / stats['total'] * 100, 1)

        # Calculate based on processed recipients (optional, might be more meaningful for delivery/read)
        if base > 0: # Check if any were processed
            stats['delivered_pct'] = round((stats['delivered'] + stats['read']) / base * 100, 1)
            stats['read_pct'] = round(stats['read'] / base * 100, 1)
            stats['failed_pct'] = round(stats['failed'] / base * 100, 1)


    # Only show upload form if campaign is in Draft status
    # Ensure ContactUploadForm is defined in forms.py
    upload_form = ContactUploadForm() if campaign.status == 'DRAFT' else None

    context = {
        'campaign': campaign,
        'recipients': recipients, # Pass the queryset for iteration in template
        'stats': stats,
        'upload_form': upload_form,
        'celery_enabled': CELERY_ENABLED, # Inform template if Celery is available
    }
    # Assuming template path
    return render(request, 'whatsapp/marketing/campaign_detail.html', context)

@user_passes_test(is_staff_user)
def campaign_create(request):
    """Handles creation of a new marketing campaign."""
    if request.method == 'POST':
        form = MarketingCampaignForm(request.POST)
        if form.is_valid():
            try:
                campaign = form.save(commit=False)
                # campaign.created_by = request.user # If tracking creator
                campaign.status = 'DRAFT' # Start as draft
                campaign.save()
                messages.success(request, f"Campaign '{campaign.name}' created successfully. Now upload contacts and schedule.")
                return redirect('whatsapp_app:campaign_detail', pk=campaign.pk) # Redirect to detail page
            except Exception as e:
                 logger.error(f"Error creating campaign: {e}")
                 messages.error(request, "An error occurred while creating the campaign.")
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = MarketingCampaignForm()

    context = {'form': form}
    return render(request, 'whatsapp/marketing/campaign_form.html', context)


@user_passes_test(is_staff_user)
@require_POST # Ensure this view is accessed via POST from the detail page form
def upload_contacts_for_campaign(request, pk):
    """Handles CSV contact upload for a draft campaign."""
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    # Allow upload only if campaign is in draft status
    if campaign.status != 'DRAFT':
        messages.error(request, "Contacts can only be uploaded for campaigns in 'Draft' status.")
        return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

    form = ContactUploadForm(request.POST, request.FILES)

    if form.is_valid():
        csv_file = request.FILES['contact_file']
        # Basic file type check
        if not csv_file.name.lower().endswith('.csv'):
             messages.error(request, 'Invalid file type. Please upload a CSV file.')
             return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

        # --- Process CSV ---
        added_count = 0
        skipped_count = 0
        invalid_waid_count = 0
        line_num = 1 # Start from 1 for header
        contacts_to_process = [] # Store validated data before bulk creation

        try:
            # Decode using utf-8-sig to handle potential Byte Order Mark (BOM)
            file_data = csv_file.read().decode('utf-8-sig')
            io_string = io.StringIO(file_data)
            reader = csv.reader(io_string)

            # Read and validate header row
            header = next(reader)
            header_lower = [h.lower().strip() for h in header]
            if 'wa_id' not in header_lower:
                 messages.error(request, "CSV file must have a header row including a 'wa_id' column.")
                 return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

            # Find column indices (case-insensitive)
            try:
                wa_id_index = header_lower.index('wa_id')
                # Optional 'name' column
                name_index = header_lower.index('name') if 'name' in header_lower else -1
                # Identify variable columns (simple approach: assume others are {{1}}, {{2}}, etc.)
                # Map header name (if 'var1', 'var2') or column index (fallback) to template variable number '1', '2', ...
                var_map = {}
                current_var_num = 1
                for idx, col_name in enumerate(header_lower):
                    if idx not in [wa_id_index, name_index]:
                         # Prefer mapping like 'var1' -> '1', 'var2' -> '2' if header exists
                         if col_name.startswith('var') and col_name[3:].isdigit():
                              var_num_str = col_name[3:]
                         else:
                              # Fallback to column order for variable number
                              var_num_str = str(current_var_num)
                              current_var_num += 1
                         var_map[var_num_str] = idx # Map template var number ('1') to column index

            except ValueError as e:
                 messages.error(request, f"Missing expected column in CSV header: {e}")
                 return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

            # Process each data row
            for row in reader:
                line_num += 1
                if not row or len(row) <= wa_id_index or not row[wa_id_index].strip():
                    # logger.debug(f"Skipping empty row {line_num} in CSV for campaign {pk}")
                    continue # Skip empty rows or rows missing wa_id

                wa_id = row[wa_id_index].strip()
                # Basic phone number format validation (digits only, reasonable length)
                if not wa_id.isdigit() or len(wa_id) < 10 or len(wa_id) > 15:
                     logger.warning(f"Skipping invalid wa_id format '{wa_id}' on line {line_num} for campaign {pk}")
                     invalid_waid_count += 1
                     continue

                # Extract name if column exists and row has enough elements
                name = row[name_index].strip() if name_index != -1 and len(row) > name_index else None

                # Extract variables based on the identified map
                variables = {}
                for var_num_str, col_idx in var_map.items():
                    if len(row) > col_idx:
                        variables[var_num_str] = row[col_idx].strip()
                    else:
                        variables[var_num_str] = "" # Use empty string if column is missing for this row

                # Add validated data to list for bulk processing
                contacts_to_process.append({
                    'wa_id': wa_id,
                    'name': name,
                    'variables': variables or None # Store None if empty
                })

            # --- Add to Database within a transaction ---
            # Consider background task for very large files (> ~5000 rows)
            if contacts_to_process:
                with transaction.atomic():
                    for item in contacts_to_process:
                        # Get or create the main Contact object
                        contact, contact_created = Contact.objects.get_or_create(wa_id=item['wa_id'])
                        # Update contact name if provided and missing or different
                        if item['name'] and (contact_created or contact.name != item['name']):
                            contact.name = item['name']
                            contact.save(update_fields=['name'])

                        # Create CampaignContact, ignore duplicates for this campaign
                        _, cc_created = CampaignContact.objects.get_or_create(
                            campaign=campaign,
                            contact=contact,
                            defaults={'template_variables': item['variables']}
                        )
                        if cc_created:
                            added_count += 1
                        else:
                            skipped_count += 1 # Already existed for this campaign

            # --- Provide Feedback ---
            if added_count > 0:
                messages.success(request, f"Processed CSV: Added {added_count} new recipients.")
            if skipped_count > 0:
                 messages.info(request, f"Skipped {skipped_count} duplicate recipients for this campaign.")
            if invalid_waid_count > 0:
                 messages.warning(request, f"Skipped {invalid_waid_count} rows due to invalid 'wa_id' format.")
            if added_count == 0 and skipped_count == 0 and invalid_waid_count == 0:
                 messages.info(request, "CSV processed, but no new valid recipients were found to add.")


        except UnicodeDecodeError:
            logger.error(f"UnicodeDecodeError processing CSV for campaign {pk}. File may not be UTF-8.")
            messages.error(request, "Could not read file. Please ensure it is saved in UTF-8 format.")
        except csv.Error as e:
             logger.error(f"CSV formatting error processing file for campaign {pk} near line {line_num}: {e}")
             messages.error(request, f"Error reading CSV file structure near line {line_num}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error processing CSV for campaign {pk}: {e}") # Log full traceback
            messages.error(request, f"An unexpected error occurred while processing the file: {e}")

    else:
        # Form is invalid (e.g., no file uploaded or wrong file type)
        for field, errors_list in form.errors.items():
            for error in errors_list:
                messages.error(request, f"{form.fields[field].label if field != '__all__' else ''}: {error}")

    # Redirect back to the campaign detail page regardless of outcome
    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)


@user_passes_test(is_staff_user)
@require_POST
def schedule_campaign(request, pk):
    """Schedules or starts sending a campaign immediately via Celery."""
    if not CELERY_ENABLED:
        messages.error(request, "Background task processing (Celery) is not enabled. Cannot schedule or send campaigns.")
        return redirect('whatsapp_app:campaign_detail', pk=pk)

    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    if campaign.status not in ['DRAFT', 'SCHEDULED', 'CANCELLED']: # Allow rescheduling cancelled?
        messages.error(request, "Campaign cannot be scheduled or sent in its current state.")
        return redirect('whatsapp_app:campaign_detail', pk=pk)

    # Ensure there are recipients added before allowing scheduling/sending
    if not CampaignContact.objects.filter(campaign=campaign).exists():
         messages.error(request, "Cannot schedule campaign: No contacts have been uploaded yet.")
         return redirect('whatsapp_app:campaign_detail', pk=pk)

    scheduled_time_str = request.POST.get('scheduled_time') # From datetime-local input

    if not scheduled_time_str:
        # --- Send immediately ---
        try:
            with transaction.atomic():
                campaign.scheduled_time = None # Clear any previous schedule
                campaign.status = 'SENDING'    # Mark as sending
                campaign.started_at = timezone.now()
                campaign.completed_at = None # Ensure completed is null
                campaign.save(update_fields=['scheduled_time', 'status', 'started_at', 'completed_at'])
                # Trigger Celery task to start processing
                send_bulk_campaign_messages_task.delay(campaign.id)
            logger.info(f"Campaign '{campaign.name}' (ID: {pk}) queued for immediate sending.")
            messages.success(request, f"Campaign '{campaign.name}' sending started.")
        except Exception as e:
             logger.error(f"Error initiating immediate send for campaign {pk}: {e}")
             messages.error(request, "An error occurred while trying to start the campaign.")

    else:
        # --- Schedule for later ---
        try:
            # Parse the datetime string from the input (e.g., 'YYYY-MM-DDTHH:MM')
            scheduled_time = parse_datetime(scheduled_time_str)
            if not scheduled_time: raise ValueError("Invalid format")

            # Ensure it's timezone-aware using the project's default timezone
            default_tz = timezone.get_default_timezone()
            if timezone.is_naive(scheduled_time):
                scheduled_time = timezone.make_aware(scheduled_time, default_tz)
            else: # If already aware, convert to default TZ just in case
                scheduled_time = scheduled_time.astimezone(default_tz)


            # Validate that the scheduled time is in the future
            if scheduled_time <= timezone.now():
                messages.error(request, "Scheduled time must be in the future.")
                return redirect('whatsapp_app:campaign_detail', pk=pk)

            with transaction.atomic():
                campaign.scheduled_time = scheduled_time
                campaign.status = 'SCHEDULED'
                campaign.started_at = None # Clear started time if rescheduling
                campaign.completed_at = None
                campaign.save(update_fields=['scheduled_time', 'status', 'started_at', 'completed_at'])

            # Optional: Schedule Celery task directly using ETA if NOT using Celery Beat
            # send_bulk_campaign_messages_task.apply_async(args=[campaign.id], eta=scheduled_time)
            # If using Celery Beat, the periodic task will pick up campaigns with status='SCHEDULED' and due scheduled_time.
            logger.info(f"Campaign '{campaign.name}' (ID: {pk}) scheduled for {scheduled_time}.")
            messages.success(request, f"Campaign '{campaign.name}' scheduled successfully for {scheduled_time.strftime('%Y-%m-%d %H:%M %Z')}.")

        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid schedule time format for campaign {pk}: '{scheduled_time_str}' - {e}")
            messages.error(request, "Invalid date/time format provided for scheduling. Please use YYYY-MM-DDTHH:MM.")
        except Exception as e:
             logger.error(f"Error scheduling campaign {pk}: {e}")
             messages.error(request, "An error occurred while trying to schedule the campaign.")


    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

@user_passes_test(is_staff_user)
@require_POST
def cancel_campaign(request, pk):
    """Cancels a campaign that is currently in 'Scheduled' status."""
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    if campaign.status == 'SCHEDULED':
        try:
            with transaction.atomic():
                campaign.status = 'CANCELLED'
                campaign.scheduled_time = None # Clear schedule time
                campaign.save(update_fields=['status', 'scheduled_time'])
            logger.info(f"Scheduled campaign '{campaign.name}' (ID: {pk}) cancelled by user {request.user}.")
            messages.info(request, f"Scheduled campaign '{campaign.name}' has been cancelled.")
            # Optional: If using Celery's apply_async with ETA, you might need to revoke the specific task.
            # This requires storing the task ID when scheduling.
            # revoke_celery_task_if_needed(campaign.id)
        except Exception as e:
             logger.error(f"Error cancelling campaign {pk}: {e}")
             messages.error(request, "An error occurred while trying to cancel the campaign.")
    else:
        messages.error(request, "Only campaigns with status 'Scheduled' can be cancelled.")

    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

@user_passes_test(is_staff_user)
@require_POST # Ensures this view only accepts POST requests
def campaign_delete(request, pk):
    """Deletes a specific marketing campaign."""
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    campaign_name = campaign.name # Get name before deleting

    # Optional: Add checks here to prevent deletion of active/sent campaigns if needed
    # if campaign.status not in ['DRAFT', 'FAILED', 'CANCELLED']:
    #     messages.error(request, f"Cannot delete campaign '{campaign_name}' because it is currently {campaign.status.lower()}.")
    #     return redirect('whatsapp_app:campaign_list')

    try:
        campaign.delete()
        # Note: Consider what should happen to associated CampaignContact records.
        # By default, they might cascade delete if ForeignKey has on_delete=models.CASCADE.
        # If you want to keep contacts but remove them from the campaign, handle that logic here.
        messages.success(request, f"Campaign '{campaign_name}' deleted successfully.")
        logger.info(f"Marketing campaign {pk} ('{campaign_name}') deleted by user {request.user.username}")
    except Exception as e:
        logger.exception(f"Error deleting marketing campaign {pk}: {e}") # Use logger.exception
        messages.error(request, "An error occurred while deleting the campaign.")

    # Redirect back to the list view in either case (success or error)
    return redirect('whatsapp_app:campaign_list')

@user_passes_test(is_staff_user)
def template_list(request):
    """Displays synced WhatsApp message templates."""
    templates = MarketingTemplate.objects.order_by('name', 'language')
    context = {'templates': templates}
    return render(request, 'whatsapp/marketing/template_list.html', context)


@user_passes_test(is_staff_user)
@require_POST # Ensure this is triggered by a POST request (e.g., from a button in a form)
def sync_whatsapp_templates(request):
    """Fetches approved templates from WhatsApp API and updates the local DB."""
    synced_count = 0
    created_count = 0
    try:
        settings = get_active_whatsapp_settings() # Raises ValueError if not configured
        templates_data = fetch_whatsapp_templates_from_api(settings) # Returns list or None

        if templates_data is None: # Indicates an API fetch error (logged in util)
            messages.error(request, "Failed to fetch templates from WhatsApp API. Check credentials, network, and API status.")
            return redirect('whatsapp_app:template_list')

        if not templates_data:
             messages.info(request, "No approved templates found in your WhatsApp Business Account.")
             return redirect('whatsapp_app:template_list')


        with transaction.atomic():
            # Get existing template keys (name, language) for efficient checking
            existing_templates = set(MarketingTemplate.objects.values_list('name', 'language'))
            api_template_keys = set()

            for template_info in templates_data:
                # Validate required fields from API response
                name = template_info.get('name')
                language = template_info.get('language')
                category = template_info.get('category')
                components = template_info.get('components')
                status = template_info.get('status') # Check status from API

                # Only process templates with necessary info and APPROVED status
                if not all([name, language, category, components, status]) or status != 'APPROVED':
                    logger.warning(f"Skipping incomplete or non-approved template data from API: Name='{name}', Lang='{language}', Status='{status}'")
                    continue

                api_template_keys.add((name, language)) # Track keys found in API

                # Use update_or_create to add new or update existing based on name and language
                obj, created = MarketingTemplate.objects.update_or_create(
                    name=name,
                    language=language,
                    defaults={
                        'category': category.upper(), # Standardize category case
                        'components': components,
                        'last_synced': timezone.now()
                    }
                )
                synced_count += 1
                if created:
                    created_count += 1

            # Optional: Delete local templates that are no longer present/approved in the API
            # stale_templates = existing_templates - api_template_keys
            # if stale_templates:
            #     deleted_count, _ = MarketingTemplate.objects.filter(name__in=[k[0] for k in stale_templates], language__in=[k[1] for k in stale_templates]).delete()
            #     logger.info(f"Deleted {deleted_count} stale templates not found in API sync.")
            #     messages.info(request, f"Removed {deleted_count} templates that are no longer approved/exist in Meta.")


        if created_count > 0:
             messages.success(request, f"Template sync complete: Added {created_count} new templates. Updated {synced_count - created_count}.")
        elif synced_count > 0:
             messages.success(request, f"Template sync complete: Updated {synced_count} existing templates. No new templates found.")
        else:
             messages.info(request, "Template sync complete: No changes detected.")


    except ValueError as e: # Catch config errors from get_active_whatsapp_settings
         logger.error(f"Configuration error during template sync: {e}")
         messages.error(request, f"Configuration Error: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during WhatsApp template sync: {e}") # Log full traceback
        messages.error(request, f"An unexpected error occurred during sync: {e}")

    return redirect('whatsapp_app:template_list')


# --- Optional Views for Bot/Auto-Reply Management ---
# Add views here if you want dedicated CRUD interfaces instead of just using Django Admin
# Example:
@user_passes_test(is_staff_user)
def bot_response_list(request):
    """Lists all configured bot responses."""
    bot_responses = BotResponse.objects.order_by('trigger_phrase')
    context = {'bot_responses': bot_responses}
    # This should render the LIST template, not the FORM template
    # return render(request, 'whatsapp/bot/bot_response_form.html', context) # Incorrect
    return render(request, 'whatsapp/bot/bot_list.html', context)

@user_passes_test(is_staff_user) 
@user_passes_test(is_staff_user)
def bot_response_create(request):
    """Creates a new bot response."""
    if request.method == 'POST':
        form = BotResponseForm(request.POST)
        if form.is_valid():
            try:
                bot_response = form.save()
                messages.success(request, f"Bot response for trigger '{bot_response.trigger_phrase}' created successfully.")
                 # Correct redirect URL name assumed
                return redirect('whatsapp_app:bot_list')
            except Exception as e:
                logger.error(f"Error creating bot response: {e}")
                messages.error(request, "An error occurred while creating the bot response.")
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = BotResponseForm()

    context = {'form': form, 'action': 'Create'}
     # Correct template path assumed
    return render(request, 'whatsapp/bot/bot_response_form.html', context)

@user_passes_test(is_staff_user)
def bot_response_update(request, pk):
    """Updates an existing bot response."""
    bot_response = get_object_or_404(BotResponse, pk=pk)
    
    if request.method == 'POST':
        form = BotResponseForm(request.POST, instance=bot_response)
        if form.is_valid():
            try:
                bot_response = form.save()
                messages.success(request, f"Bot response for trigger '{bot_response.trigger_phrase}' updated successfully.")
                return redirect('whatsapp:bot_response_list')
            except Exception as e:
                logger.error(f"Error updating bot response {pk}: {e}")
                messages.error(request, "An error occurred while updating the bot response.")
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = BotResponseForm(instance=bot_response)
    
    context = {
        'form': form,
        'bot_response': bot_response,
        'action': 'Update'
    }
    return render(request, 'whatsapp/bot/bot_response_form.html', context)

@user_passes_test(is_staff_user)
def autoreply_settings_view(request):
    """Manages auto-reply settings."""
    try:
        settings = AutoReply.objects.first()
    except AutoReply.DoesNotExist:
        settings = None
        
    if request.method == 'POST':
        form = AutoReplySettingsForm(request.POST, instance=settings)
        if form.is_valid():
            try:
                settings = form.save()
                messages.success(request, "Auto-reply settings updated successfully.")
                return redirect('whatsapp:autoreply_settings')
            except Exception as e:
                logger.error(f"Error saving auto-reply settings: {e}")
                messages.error(request, "An error occurred while saving auto-reply settings.")
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = AutoReplySettingsForm(instance=settings)
    
    context = {
        'form': form,
        'settings': settings
    }
    return render(request, 'whatsapp/bot/autoreply_settings.html', context)
@user_passes_test(is_staff_user)
@require_POST # Ensures this view only accepts POST requests
def bot_response_delete(request, pk):
    """Deletes a specific bot response."""
    bot_response = get_object_or_404(BotResponse, pk=pk)
    trigger_phrase = bot_response.trigger_phrase # Get phrase before deleting

    try:
        bot_response.delete()
        messages.success(request, f"Bot response for trigger '{trigger_phrase}' deleted successfully.")
        logger.info(f"Bot response {pk} ('{trigger_phrase}') deleted by user {request.user.username}")
    except Exception as e:
        logger.error(f"Error deleting bot response {pk}: {e}")
        messages.error(request, "An error occurred while deleting the bot response.")

    # Redirect back to the list view in either case (success or error)
     # Correct redirect URL name assumed
    return redirect('whatsapp_app:bot_list')
