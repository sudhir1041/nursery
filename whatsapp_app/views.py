
# --- Django Imports ---
from django.shortcuts import render, redirect, get_object_or_404
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
from django.urls import reverse

# --- Standard Library Imports ---
import json
import csv
import io
import logging
import uuid # For webhook token generation if needed
import hmac # For signature verification
import hashlib # For signature verification

# --- App Imports ---
# Models from this app
from .models import (
    Contact, ChatMessage, WhatsAppSettings, BotResponse, AutoReply,
    MarketingTemplate, MarketingCampaign, CampaignContact,
)
# Forms from this app
from .forms import (
    WhatsAppSettingsForm, ManualMessageForm, MarketingCampaignForm,
    ContactUploadForm , BotResponseForm, AutoReplySettingsForm,AddContactForm # Ensure ManualMessageForm is defined
)
# Utilities from this app (Assume these exist and handle API/parsing logic)
from .utils import (
    send_whatsapp_message, parse_incoming_whatsapp_message,
    fetch_whatsapp_templates_from_api, get_active_whatsapp_settings,
    verify_whatsapp_signature # Add this utility if implementing signature verification
)

# --- Celery (Optional Background Tasks) ---
try:
    # Import the tasks needed by views
    from .tasks import process_whatsapp_webhook_task, send_bulk_campaign_messages_task, send_whatsapp_message_task
    CELERY_ENABLED = True
except ImportError:
    CELERY_ENABLED = False
    # Define dummy task functions if Celery is not installed/enabled
    def process_whatsapp_webhook_task(*args, **kwargs):
        logger.error("Celery not configured. Cannot run process_whatsapp_webhook_task.")
        # Depending on how critical, you might raise error or just log
    def send_bulk_campaign_messages_task(*args, **kwargs):
        logger.error("Celery not configured. Cannot run send_bulk_campaign_messages_task.")
        raise NotImplementedError("Celery is not enabled or tasks are not defined.")
    def send_whatsapp_message_task(*args, **kwargs):
        logger.error("Celery not configured. Cannot run send_whatsapp_message_task.")
        raise NotImplementedError("Celery is not enabled or tasks are not defined.")

# --- Logger Setup ---
logger = logging.getLogger(__name__)

# --- Helper: Check if user is admin/staff ---
def is_staff_user(user):
    """ Checks if the user is authenticated and has staff privileges. """
    # Implement your actual permission logic here
    return user.is_authenticated and user.is_staff

# ==============================================================================
# Dashboard View
# ==============================================================================
@user_passes_test(is_staff_user)
def dashboard(request):
    """ Displays overview statistics related to WhatsApp integration. """
    today = timezone.now().date()
    stats = {}
    try:
        stats['total_contacts'] = Contact.objects.count()
        stats['active_chats_count'] = Contact.objects.filter(messages__isnull=False).distinct().count()
        messages_today_qs = ChatMessage.objects.filter(timestamp__date=today)
        stats['messages_today'] = messages_today_qs.count()
        stats['incoming_today'] = messages_today_qs.filter(direction='IN').count()
        stats['outgoing_today'] = messages_today_qs.filter(direction='OUT').count()
        outgoing_messages = ChatMessage.objects.filter(direction='OUT')
        total_outgoing = outgoing_messages.count()
        delivered_count = outgoing_messages.filter(status__in=['DELIVERED', 'READ']).count()
        failed_count = outgoing_messages.filter(status='FAILED').count()
        stats['success_rate'] = (delivered_count / total_outgoing * 100) if total_outgoing > 0 else 0
        stats['failed_count'] = failed_count
        stats['recent_campaigns'] = MarketingCampaign.objects.select_related('template').order_by('-created_at')[:5]
    except Exception as e:
        logger.exception(f"Error fetching dashboard stats: {e}") # Log full traceback
        messages.error(request, "Could not load all dashboard statistics.")
        stats.setdefault('total_contacts', 0)
        stats.setdefault('active_chats_count', 0)
        stats.setdefault('messages_today', 0)
        stats.setdefault('incoming_today', 0)
        stats.setdefault('outgoing_today', 0)
        stats.setdefault('success_rate', 0)
        stats.setdefault('failed_count', 0)
        stats.setdefault('recent_campaigns', [])
    context = stats
    return render(request, 'whatsapp/dashboard.html', context)


# ==============================================================================
# Settings View
# ==============================================================================
@user_passes_test(is_staff_user)
def whatsapp_settings_view(request):
    """ Manages WhatsApp Cloud API connection settings. """
    settings_name = "NurseryProjectDefault"
    settings_instance, created = WhatsAppSettings.objects.get_or_create(
        account_name=settings_name,
        defaults={'webhook_verify_token': str(uuid.uuid4())}
    )
    if request.method == 'POST':
        form = WhatsAppSettingsForm(request.POST, instance=settings_instance)
        if form.is_valid():
            try:
                settings = form.save()
                messages.success(request, 'WhatsApp API settings saved successfully.')
                if form.has_changed() and any(field in form.changed_data for field in ['webhook_url', 'webhook_verify_token']):
                    messages.info(request, "Remember to update the Webhook URL and Verify Token in the Meta Developer Portal for your WhatsApp App.")
                return redirect('whatsapp_app:settings')
            except Exception as e:
                logger.exception(f"Error saving WhatsApp settings: {e}")
                messages.error(request, f"Failed to save settings: {e}")
        else:
            messages.error(request, "Please correct the errors highlighted below.")
    else:
        form = WhatsAppSettingsForm(instance=settings_instance)

    full_webhook_url = None
    if settings_instance:
        try:
            webhook_path = reverse('whatsapp_app:webhook_handler')
            full_webhook_url = request.build_absolute_uri(webhook_path)
        except Exception as e:
            logger.warning(f"Could not reverse URL for 'whatsapp_app:webhook_handler'. Check urls.py. Error: {e}")

    context = {
        'form': form,
        'settings': settings_instance,
        'full_webhook_url': full_webhook_url
    }
    return render(request, 'whatsapp/settings_form.html', context)


# ==============================================================================
# Webhook Handler (Updated for Celery)
# ==============================================================================
@csrf_exempt # WhatsApp doesn't send CSRF tokens
def webhook_handler(request):
    """ Handles incoming notifications (messages, status updates) from WhatsApp. """

    # 1. Verify Signature (Recommended for Production)
    app_secret = getattr(django_settings, 'WHATSAPP_APP_SECRET', None)
    if app_secret:
        signature = request.headers.get('X-Hub-Signature-256')
        # Ensure verify_whatsapp_signature utility exists and works
        if not signature or not verify_whatsapp_signature(request.body, signature, app_secret):
            logger.warning("Invalid webhook signature received.")
            return HttpResponseForbidden("Invalid signature.")
    else:
        if not django_settings.DEBUG:
             logger.warning("WHATSAPP_APP_SECRET not configured. Skipping webhook signature verification (INSECURE).")

    # 2. Handle Verification Request (GET)
    if request.method == 'GET':
        verify_token_param = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        mode = request.GET.get('hub.mode')

        if mode == 'subscribe' and verify_token_param and challenge:
            try:
                settings = get_active_whatsapp_settings() # Ensure this util exists
                expected_token = settings.webhook_verify_token
                if verify_token_param == expected_token:
                    logger.info(f"Webhook verification successful. Responding with challenge: {challenge}")
                    return HttpResponse(challenge, status=200)
                else:
                    logger.warning(f"Webhook verification failed. Received token: '{verify_token_param}', Expected: '{expected_token}'")
                    return HttpResponseForbidden("Verification token mismatch.")
            # Specific exceptions first
            except WhatsAppSettings.DoesNotExist:
                logger.error("Webhook verification failed: WhatsAppSettings not found.")
                return HttpResponseForbidden("Configuration error: Settings not found.")
            except ValueError as e: # Catches config errors from get_active_whatsapp_settings
                 logger.error(f"Webhook verification failed: Configuration error - {e}")
                 return HttpResponseForbidden(f"Configuration error: {e}")
            except Exception as e: # Catch broader exceptions
                logger.exception(f"Error during webhook GET verification: {e}") # Log traceback
                return HttpResponseForbidden("Internal server error during verification.")
        else:
             logger.warning(f"Invalid GET verification request parameters received: Mode='{mode}', Token Provided='{bool(verify_token_param)}', Challenge Provided='{bool(challenge)}'")
             return HttpResponseBadRequest("Invalid verification request.")


    # 3. Handle Incoming Notifications (POST) - Queue Celery Task
    if request.method == 'POST':
        try:
            # Get raw body for signature verification AND parsing by task
            raw_body = request.body
            # Basic check if body is empty
            if not raw_body:
                 logger.warning("Received empty POST request body in webhook.")
                 return HttpResponseBadRequest("Empty request body.")

            # Decode body to pass as string to Celery (JSON serialization best practice)
            payload_str = raw_body.decode('utf-8')

            # Log before queuing (consider sampling or reducing log level in production)
            logger.info(f"Webhook POST received. Queueing processing task.")
            # logger.debug(f"Webhook payload for task: {payload_str}") # Debug level for full payload

            # --- Trigger Celery Task ---
            if CELERY_ENABLED:
                process_whatsapp_webhook_task.delay(payload_str=payload_str)
            else:
                # Fallback if Celery is not enabled (Process synchronously - less ideal)
                logger.warning("Celery not enabled. Processing webhook synchronously.")
                try:
                    payload = json.loads(payload_str)
                    processed_data = parse_incoming_whatsapp_message(payload)
                    if processed_data and processed_data.get('type') == 'incoming_message':
                        message_obj = processed_data.get('message_object')
                        if message_obj and isinstance(message_obj, ChatMessage):
                            handle_bot_or_autoreply(message_obj)
                except Exception as sync_e:
                     logger.exception(f"Error processing webhook synchronously: {sync_e}")
                     # Don't let internal processing error prevent 200 OK

            # Acknowledge receipt to WhatsApp IMMEDIATELY
            return HttpResponse(status=200)

        except json.JSONDecodeError:
            logger.error("Invalid JSON received in webhook POST request (before queuing).")
            # Still return 200 OK if possible, but log error
            return HttpResponse(status=200) # Or BadRequest if you prefer, but Meta might retry
        except Exception as e:
            logger.exception(f"Error before queuing webhook processing task: {e}")
            # Still return 200 OK to WhatsApp
            return HttpResponse(status=200)

    # Method Not Allowed for other HTTP verbs
    logger.warning(f"Received webhook request with unsupported method: {request.method}")
    return HttpResponse(status=405)

# ==============================================================================
# Helper Function for Bots/Auto-Replies (Called by Celery Task or Webhook Fallback)
# ==============================================================================
def handle_bot_or_autoreply(incoming_message: ChatMessage):
    """ Checks and sends bot responses or auto-replies based on incoming message. """
    if not incoming_message or not incoming_message.text_content or incoming_message.direction != 'IN':
        return # Only process incoming text messages

    contact = incoming_message.contact
    message_text_lower = incoming_message.text_content.lower().strip()
    bot_responded = False

    # 1. Check for Bot Triggers
    try:
        bot_response = BotResponse.objects.filter(is_active=True, trigger_phrase__iexact=message_text_lower).first()
        if bot_response:
            last_out_msg = ChatMessage.objects.filter(contact=contact, direction='OUT').order_by('-timestamp').first()
            # Simple loop prevention
            if not last_out_msg or last_out_msg.text_content != bot_response.response_text:
                # Call utility to send the message
                send_whatsapp_message(recipient_wa_id=contact.wa_id, message_type='text', text_content=bot_response.response_text)
                logger.info(f"Sent bot response for trigger '{bot_response.trigger_phrase}' to {contact.wa_id}")
                bot_responded = True
            else:
                 logger.info(f"Skipping bot response for '{bot_response.trigger_phrase}' to {contact.wa_id} to prevent potential loop.")
                 bot_responded = True # Still consider handled
    except Exception as e:
        logger.exception(f"Error checking/sending bot response for {contact.wa_id}: {e}") # Log full traceback

    # 2. Check for Auto-Reply (Only if no bot response was sent)
    if not bot_responded:
        # <<<--- IMPLEMENT YOUR AGENT AVAILABILITY LOGIC HERE --- >>>
        # Example: Check business hours, check if any staff user was recently active in this chat, etc.
        agent_available = False # Default to unavailable for this example

        if not agent_available:
            try:
                # Use get() assuming singleton pk=1, handle DoesNotExist
                auto_reply_settings = AutoReply.objects.get(pk=1, is_active=True)
                if auto_reply_settings:
                    last_out_msg = ChatMessage.objects.filter(contact=contact, direction='OUT').order_by('-timestamp').first()
                     # Simple loop prevention
                    if not last_out_msg or last_out_msg.text_content != auto_reply_settings.message_text:
                        send_whatsapp_message(recipient_wa_id=contact.wa_id, message_type='text', text_content=auto_reply_settings.message_text)
                        logger.info(f"Sent auto-reply to {contact.wa_id}")
                    else:
                        logger.info(f"Skipping auto-reply to {contact.wa_id} to prevent potential loop.")
            except AutoReply.DoesNotExist:
                 logger.info("Auto-reply is not configured or not active.") # Expected if not set up
            except Exception as e:
                logger.exception(f"Error checking/sending auto-reply for {contact.wa_id}: {e}") # Log full traceback


# ==============================================================================
# Chat List & Detail Views
# ==============================================================================
@user_passes_test(is_staff_user)
def chat_list(request):
    """ Displays a list of contacts with recent chat activity. """
    search_query = request.GET.get('q', '').strip()

    # Get contacts, ordered by the timestamp of their last message
    # Annotate with last message time for ordering
    contacts_with_messages = Contact.objects.annotate(
        last_message_time=Max('messages__timestamp')
        ).filter(last_message_time__isnull=False) 

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
    # Ensure the template path matches your project structure
    return render(request, 'whatsapp/chat_list.html', context)

@user_passes_test(is_staff_user)
def chat_detail(request, wa_id):
    """ Displays the message history for a specific contact and allows sending messages. """
    contact = get_object_or_404(Contact, wa_id=wa_id)
    messages_qs = ChatMessage.objects.filter(contact=contact).order_by('timestamp')
    form = ManualMessageForm() # Ensure ManualMessageForm is defined in forms.py

    # Get the timestamp of the very last message for AJAX polling/WebSocket initial state
    last_msg = messages_qs.last()
    last_message_timestamp_iso = last_msg.timestamp.isoformat() if last_msg else timezone.now().isoformat()

    context = {
        'contact': contact,
        'messages': messages_qs,
        'form': form,
        'last_message_timestamp': last_message_timestamp_iso,
    }
    return render(request, 'whatsapp/chat_detail.html', context)

# ==============================================================================
# AJAX Endpoints for Chat (Used by chat.js)
# ==============================================================================
@user_passes_test(is_staff_user)
@require_POST
def send_manual_message_ajax(request):
    """
    AJAX endpoint to send a manual message.
    Queues a Celery task if enabled, otherwise sends synchronously.
    NOTE: This endpoint might be less relevant if using WebSockets for sending.
          It primarily serves the AJAX polling version of chat.js or non-JS fallbacks.
    """
    wa_id = request.POST.get('wa_id')
    if not wa_id:
         return JsonResponse({'status': 'error', 'message': 'Missing wa_id parameter.'}, status=400)

    contact = get_object_or_404(Contact, wa_id=wa_id)
    form = ManualMessageForm(request.POST) # Assumes form contains 'text_content'
    if form.is_valid():
        message_text = form.cleaned_data['text_content']
        
        # Check if same message was sent recently to prevent duplicates
        recent_message = ChatMessage.objects.filter(
            contact=contact,
            text_content=message_text,
            direction='OUT',
            timestamp__gte=timezone.now() - timezone.timedelta(minutes=1)
        ).exists()
        
        if recent_message:
            logger.warning(f"Duplicate message detected for wa_id: {wa_id}. Skipping send.")
            return JsonResponse({'status': 'error', 'message': 'Duplicate message detected. Please wait before sending the same message again.'}, status=400)
            
        try:
            # --- Trigger Celery task to send message ---
            if CELERY_ENABLED:
                send_whatsapp_message_task.delay(
                    recipient_wa_id=contact.wa_id,
                    message_type='text',
                    text_content=message_text
                )
                # Return success immediately after queuing
                logger.info(f"AJAX send success (task queued) for wa_id: {wa_id}")
                return JsonResponse({'status': 'success', 'message': 'Message queued for sending.'})
            else:
                # Fallback: Send synchronously if Celery is disabled
                logger.warning("Celery not enabled. Sending message synchronously.")
                message_obj = send_whatsapp_message(
                    recipient_wa_id=contact.wa_id,
                    message_type='text',
                    text_content=message_text
                )
                if message_obj:
                     logger.info(f"AJAX send success (sent sync) for wa_id: {wa_id}. Message ID: {message_obj.message_id}")
                     # Return details of the sent message
                     return JsonResponse({
                         'status': 'success',
                         'message': { # Return the created message object details
                             'message_id': message_obj.message_id, 'text_content': message_obj.text_content,
                             'timestamp': message_obj.timestamp.isoformat(), 'direction': 'OUT',
                             'status': message_obj.status, 'message_type': message_obj.message_type,
                             'template_name': message_obj.template_name, 'media_url': message_obj.media_url,
                         }
                     })
                else:
                    logger.error(f"AJAX send FAILED (sync send utility returned None) for wa_id: {wa_id}")
                    return JsonResponse({'status': 'error', 'message': 'Failed to send message synchronously.'}, status=500)

        except Exception as e:
            logger.exception(f"Error triggering send task or sending synchronously for {wa_id}: {e}")
            return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred.'}, status=500)
    else:
        # Form validation failed
        logger.warning(f"Manual message form validation failed for {wa_id}: {form.errors.as_json()}")
        return JsonResponse({'status': 'error', 'message': 'Invalid form data'}, status=400)

@user_passes_test(is_staff_user)
@require_GET
def get_latest_messages_ajax(request):
    wa_id = request.GET.get('wa_id'); last_timestamp_str = request.GET.get('last_timestamp')
    if not wa_id or not last_timestamp_str: return JsonResponse({'status': 'error', 'message': 'Missing parameters'}, status=400)
    logger.debug(f"AJAX poll request received for wa_id: {wa_id} after timestamp: {last_timestamp_str}")
    try:
        contact = Contact.objects.get(wa_id=wa_id); last_timestamp = parse_datetime(last_timestamp_str)
        if not last_timestamp: logger.warning(f"Invalid timestamp format: {last_timestamp_str}"); return JsonResponse({'status': 'error', 'message': 'Invalid timestamp format'}, status=400)
        if timezone.is_naive(last_timestamp): last_timestamp = timezone.make_aware(last_timestamp, timezone.get_default_timezone())
        logger.debug(f"Querying messages for {wa_id} with timestamp > {last_timestamp.isoformat()}")
        new_messages_qs = ChatMessage.objects.filter(contact=contact, timestamp__gt=last_timestamp).order_by('timestamp')
        new_message_count = new_messages_qs.count(); logger.debug(f"Found {new_message_count} new messages in DB query.")
        new_messages_data = list(new_messages_qs.values('message_id', 'text_content', 'timestamp', 'direction', 'status', 'media_url', 'message_type', 'template_name'))
        latest_ts_in_response = last_timestamp
        for msg_data in new_messages_data:
            if isinstance(msg_data.get('timestamp'), timezone.datetime):
                if msg_data['timestamp'] > latest_ts_in_response: latest_ts_in_response = msg_data['timestamp']
                msg_data['timestamp'] = msg_data['timestamp'].isoformat()
        next_poll_timestamp_iso = latest_ts_in_response.isoformat()
        logger.info(f"AJAX poll returning {len(new_messages_data)} new messages for wa_id: {wa_id}. Next timestamp: {next_poll_timestamp_iso}")
        return JsonResponse({'status': 'success', 'new_messages': new_messages_data, 'next_poll_timestamp': next_poll_timestamp_iso})
    except Contact.DoesNotExist: logger.warning(f"Contact not found during poll: {wa_id}"); return JsonResponse({'status': 'error', 'message': 'Contact not found'}, status=404)
    except Exception as e: logger.exception(f"Error fetching latest messages for {wa_id}: {e}"); return JsonResponse({'status': 'error', 'message': 'Server error'}, status=500)


# ==============================================================================
# Bot Response CRUD Views
# ==============================================================================
@user_passes_test(is_staff_user)
def bot_response_list(request):
    """ Lists all configured bot responses. """
    bot_responses = BotResponse.objects.order_by('trigger_phrase')
    context = {'bot_responses': bot_responses}
    return render(request, 'whatsapp/bot/bot_list.html', context)

@user_passes_test(is_staff_user)
def bot_response_create(request):
    """ Creates a new bot response. """
    if request.method == 'POST':
        form = BotResponseForm(request.POST)
        if form.is_valid():
            try:
                bot_response = form.save()
                messages.success(request, f"Bot response for trigger '{bot_response.trigger_phrase}' created successfully.")
                return redirect('whatsapp_app:bot_list')
            except Exception as e:
                logger.error(f"Error creating bot response: {e}")
                messages.error(request, "An error occurred while creating the bot response.")
        else:
            messages.error(request, "Please correct the errors highlighted below.")
    else:
        form = BotResponseForm()
    context = {'form': form, 'action': 'Create'}
    return render(request, 'whatsapp/bot/bot_response_form.html', context)

@user_passes_test(is_staff_user)
def bot_response_update(request, pk):
    """ Updates an existing bot response. """
    bot_response = get_object_or_404(BotResponse, pk=pk)
    if request.method == 'POST':
        form = BotResponseForm(request.POST, instance=bot_response)
        if form.is_valid():
            try:
                bot_response = form.save()
                messages.success(request, f"Bot response for trigger '{bot_response.trigger_phrase}' updated successfully.")
                return redirect('whatsapp_app:bot_list')
            except Exception as e:
                logger.error(f"Error updating bot response {pk}: {e}")
                messages.error(request, "An error occurred while updating the bot response.")
        else:
            messages.error(request, "Please correct the errors highlighted below.")
    else:
        form = BotResponseForm(instance=bot_response)
    context = {'form': form, 'bot_response': bot_response, 'action': 'Update'}
    return render(request, 'whatsapp/bot/bot_response_form.html', context)

@user_passes_test(is_staff_user)
@require_POST
def bot_response_delete(request, pk):
    """ Deletes a specific bot response. """
    bot_response = get_object_or_404(BotResponse, pk=pk)
    trigger_phrase = bot_response.trigger_phrase
    try:
        bot_response.delete()
        messages.success(request, f"Bot response for trigger '{trigger_phrase}' deleted successfully.")
        logger.info(f"Bot response {pk} ('{trigger_phrase}') deleted by user {request.user.username}")
    except Exception as e:
        logger.error(f"Error deleting bot response {pk}: {e}")
        messages.error(request, "An error occurred while deleting the bot response.")
    return redirect('whatsapp_app:bot_list')


# ==============================================================================
# Auto-Reply View
# ==============================================================================
@user_passes_test(is_staff_user)
def autoreply_settings_view(request):
    """ Manages auto-reply settings. """
    settings, created = AutoReply.objects.get_or_create(pk=1) # Assuming pk=1 for singleton
    if request.method == 'POST':
        form = AutoReplySettingsForm(request.POST, instance=settings)
        if form.is_valid():
            try:
                settings = form.save()
                messages.success(request, "Auto-reply settings updated successfully.")
                return redirect('whatsapp_app:autoreply_settings')
            except Exception as e:
                logger.exception(f"Error saving auto-reply settings: {e}")
                messages.error(request, "An error occurred while saving auto-reply settings.")
        else:
            messages.error(request, "Please correct the errors highlighted below.")
    else:
        form = AutoReplySettingsForm(instance=settings)
    context = {'form': form, 'settings': settings}
    return render(request, 'whatsapp/bot/autoreply_settings.html', context)


# ==============================================================================
# Marketing Campaign Views
# ==============================================================================
@user_passes_test(is_staff_user)
def campaign_list(request):
    """ Lists all marketing campaigns. """
    campaigns = MarketingCampaign.objects.select_related('template').order_by('-created_at')
    context = {'campaigns': campaigns}
    return render(request, 'whatsapp/marketing/campaign_list.html', context)

@user_passes_test(is_staff_user)
def campaign_detail(request, pk):
    """ Shows details and recipients of a specific campaign. """
    campaign = get_object_or_404(MarketingCampaign.objects.select_related('template'), pk=pk)
    recipients = CampaignContact.objects.filter(campaign=campaign).select_related('contact').order_by('contact__wa_id')
    stats = recipients.aggregate(
        total=Count('id'), pending=Count('id', filter=Q(status='PENDING')), sent=Count('id', filter=Q(status='SENT')),
        delivered=Count('id', filter=Q(status='DELIVERED')), read=Count('id', filter=Q(status='READ')), failed=Count('id', filter=Q(status='FAILED')),
    )
    stats['sent_pct'] = 0; stats['delivered_pct'] = 0; stats['read_pct'] = 0; stats['failed_pct'] = 0
    if stats['total'] > 0:
        processed_total = stats['total'] - stats['pending']; base = processed_total if processed_total > 0 else 1
        stats['sent_pct'] = round((stats['sent'] + stats['delivered'] + stats['read'] + stats['failed']) / stats['total'] * 100, 1)
        if base > 0:
            stats['delivered_pct'] = round((stats['delivered'] + stats['read']) / base * 100, 1)
            stats['read_pct'] = round(stats['read'] / base * 100, 1)
            stats['failed_pct'] = round(stats['failed'] / base * 100, 1)
    upload_form = ContactUploadForm() if campaign.status == 'DRAFT' else None
    context = { 'campaign': campaign, 'recipients': recipients, 'stats': stats, 'upload_form': upload_form, 'celery_enabled': CELERY_ENABLED, }
    return render(request, 'whatsapp/marketing/campaign_detail.html', context)

@user_passes_test(is_staff_user)
def campaign_create(request):
    """ Handles creation of a new marketing campaign. """
    if request.method == 'POST':
        form = MarketingCampaignForm(request.POST)
        if form.is_valid():
            try:
                campaign = form.save(commit=False); campaign.status = 'DRAFT'; campaign.save()
                messages.success(request, f"Campaign '{campaign.name}' created successfully. Now upload contacts and schedule.")
                return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)
            except Exception as e:
                logger.error(f"Error creating campaign: {e}"); messages.error(request, "An error occurred while creating the campaign.")
        else: messages.error(request, "Please correct the errors highlighted below.")
    else: form = MarketingCampaignForm()
    context = {'form': form, 'action': 'Create'}
    return render(request, 'whatsapp/marketing/campaign_form.html', context)

# media file upload in chats 
@user_passes_test(is_staff_user)
@require_POST
def upload_whatsapp_media_ajax(request):
    """ Handles file uploads from chat interface, uploads to WhatsApp, returns media ID. """
    if not request.FILES.get('media_file'):
        return JsonResponse({'status': 'error', 'message': 'No media file found in request.'}, status=400)

    media_file = request.FILES['media_file']
    wa_id = request.POST.get('wa_id') # Optional: Get contact context if needed

    # TODO: Add more robust validation (file size, type server-side)

    try:
        # --- Call utility to upload to WhatsApp ---
        # This utility needs to handle the actual WhatsApp Graph API call for media uploads
        # It should return a dictionary like {'id': 'whatsapp_media_id', 'type': 'image/video/etc'} or None on failure
        upload_result = upload_media_to_whatsapp(media_file) # Implement this in utils.py

        if upload_result and upload_result.get('id'):
            logger.info(f"Successfully uploaded media for {wa_id}, received media_id: {upload_result['id']}")
            return JsonResponse({
                'status': 'success',
                'media_id': upload_result['id'],
                'media_type': upload_result.get('type', 'document') # Determine type based on file or API response
            })
        else:
            logger.error(f"Failed to upload media to WhatsApp API for {wa_id}.")
            return JsonResponse({'status': 'error', 'message': 'Failed to upload media to WhatsApp.'}, status=500)

    except Exception as e:
        logger.exception(f"Error during media upload for {wa_id}: {e}")
        return JsonResponse({'status': 'error', 'message': 'Server error during media upload.'}, status=500)
    
@user_passes_test(is_staff_user)
@require_POST
def upload_contacts_for_campaign(request, pk):
    """ Handles CSV contact upload for a draft campaign. """
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    if campaign.status != 'DRAFT':
        messages.error(request, "Contacts can only be uploaded for campaigns in 'Draft' status.")
        return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)
    form = ContactUploadForm(request.POST, request.FILES)
    if form.is_valid():
        csv_file = request.FILES['contact_file']
        if not csv_file.name.lower().endswith('.csv'):
            messages.error(request, 'Invalid file type. Please upload a CSV file.')
            return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)
        added_count = 0; skipped_count = 0; invalid_waid_count = 0; line_num = 1; contacts_to_process = []
        try:
            file_data = csv_file.read().decode('utf-8-sig'); io_string = io.StringIO(file_data); reader = csv.reader(io_string)
            header = next(reader); header_lower = [h.lower().strip() for h in header]
            if 'wa_id' not in header_lower: raise ValueError("CSV must have a 'wa_id' column.")
            wa_id_index = header_lower.index('wa_id'); name_index = header_lower.index('name') if 'name' in header_lower else -1
            var_map = {}; current_var_num = 1
            for idx, col_name in enumerate(header_lower):
                if idx not in [wa_id_index, name_index]:
                    var_num_str = col_name[3:] if col_name.startswith('var') and col_name[3:].isdigit() else str(current_var_num)
                    var_map[var_num_str] = idx; current_var_num += 1 if not (col_name.startswith('var') and col_name[3:].isdigit()) else 0
            for row in reader:
                line_num += 1
                if not row or len(row) <= wa_id_index or not row[wa_id_index].strip(): continue
                wa_id = row[wa_id_index].strip()
                if not wa_id.isdigit() or len(wa_id) < 10 or len(wa_id) > 15: invalid_waid_count += 1; continue
                name = row[name_index].strip() if name_index != -1 and len(row) > name_index else None
                variables = {var_num_str: row[col_idx].strip() if len(row) > col_idx else "" for var_num_str, col_idx in var_map.items()}
                contacts_to_process.append({'wa_id': wa_id, 'name': name, 'variables': variables or None})
            if contacts_to_process:
                with transaction.atomic():
                    for item in contacts_to_process:
                        contact, contact_created = Contact.objects.get_or_create(wa_id=item['wa_id'])
                        if item['name'] and (contact_created or contact.name != item['name']): contact.name = item['name']; contact.save(update_fields=['name'])
                        _, cc_created = CampaignContact.objects.get_or_create(campaign=campaign, contact=contact, defaults={'template_variables': item['variables']})
                        if cc_created: added_count += 1
                        else: skipped_count += 1
            if added_count > 0: messages.success(request, f"Processed CSV: Added {added_count} new recipients.")
            if skipped_count > 0: messages.info(request, f"Skipped {skipped_count} duplicate recipients for this campaign.")
            if invalid_waid_count > 0: messages.warning(request, f"Skipped {invalid_waid_count} rows due to invalid 'wa_id' format.")
            if added_count == 0 and skipped_count == 0 and invalid_waid_count == 0: messages.info(request, "CSV processed, but no new valid recipients were found to add.")
        except UnicodeDecodeError: messages.error(request, "Could not read file. Please ensure it is saved in UTF-8 format.")
        except csv.Error as e: messages.error(request, f"Error reading CSV file structure near line {line_num}: {e}")
        except ValueError as e: messages.error(request, f"Error processing CSV header: {e}") # Catch header errors
        except Exception as e: logger.exception(f"Unexpected error processing CSV for campaign {pk}: {e}"); messages.error(request, f"An unexpected error occurred: {e}")
    else:
        for field, errors_list in form.errors.items():
            for error in errors_list: messages.error(request, f"{form.fields[field].label if field != '__all__' else ''}: {error}")
    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

@user_passes_test(is_staff_user)
@require_POST
@user_passes_test(is_staff_user)
@require_POST 
@user_passes_test(is_staff_user)
@require_POST
def schedule_campaign(request, pk):
    """ Schedules or starts sending a campaign immediately via Celery. """
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    if campaign.status not in ['DRAFT', 'SCHEDULED', 'CANCELLED']:
        messages.error(request, "Campaign cannot be scheduled or sent in its current state.")
        return redirect('whatsapp_app:campaign_detail', pk=pk)
    if not CampaignContact.objects.filter(campaign=campaign).exists():
        messages.error(request, "Cannot schedule campaign: No contacts have been uploaded yet.")
        return redirect('whatsapp_app:campaign_detail', pk=pk)
    scheduled_time_str = request.POST.get('scheduled_time')
    if not scheduled_time_str: # Send immediately
        try:
            # Validate recipient contacts before sending
            invalid_contacts = []
            for contact in CampaignContact.objects.filter(campaign=campaign):
                if not contact.contact.wa_id or len(contact.contact.wa_id) < 10:
                    invalid_contacts.append(contact.contact.wa_id)
            
            if invalid_contacts:
                messages.error(request, f"Campaign contains invalid recipient numbers: {', '.join(invalid_contacts)}")
                return redirect('whatsapp_app:campaign_detail', pk=pk)
                
            with transaction.atomic():
                campaign.scheduled_time = None
                campaign.status = 'SENDING'
                campaign.started_at = timezone.now()
                campaign.completed_at = None
                campaign.save(update_fields=['scheduled_time', 'status', 'started_at', 'completed_at'])
                send_bulk_campaign_messages_task.delay(campaign.id)
            logger.info(f"Campaign '{campaign.name}' (ID: {pk}) queued for immediate sending.")
            messages.success(request, f"Campaign '{campaign.name}' sending started.")
        except Exception as e:
            logger.error(f"Error initiating immediate send for campaign {pk}: {e}")
            messages.error(request, "An error occurred while trying to start the campaign.")
    else: # Schedule for later
        try:
            scheduled_time = parse_datetime(scheduled_time_str)
            default_tz = timezone.get_default_timezone()
            if not scheduled_time:
                raise ValueError("Invalid format")
            if timezone.is_naive(scheduled_time):
                scheduled_time = timezone.make_aware(scheduled_time, default_tz)
            else:
                scheduled_time = scheduled_time.astimezone(default_tz)
            if scheduled_time <= timezone.now():
                messages.error(request, "Scheduled time must be in the future.")
                return redirect('whatsapp_app:campaign_detail', pk=pk)
                
            # Validate recipient contacts before scheduling
            invalid_contacts = []
            for contact in CampaignContact.objects.filter(campaign=campaign):
                if not contact.contact.wa_id or len(contact.contact.wa_id) < 10:
                    invalid_contacts.append(contact.contact.wa_id)
                    
            if invalid_contacts:
                messages.error(request, f"Campaign contains invalid recipient numbers: {', '.join(invalid_contacts)}")
                return redirect('whatsapp_app:campaign_detail', pk=pk)
                
            with transaction.atomic():
                campaign.scheduled_time = scheduled_time
                campaign.status = 'SCHEDULED'
                campaign.started_at = None
                campaign.completed_at = None
                campaign.save(update_fields=['scheduled_time', 'status', 'started_at', 'completed_at'])
            logger.info(f"Campaign '{campaign.name}' (ID: {pk}) scheduled for {scheduled_time}.")
            messages.success(request, f"Campaign '{campaign.name}' scheduled successfully for {scheduled_time.strftime('%Y-%m-%d %H:%M %Z')}.")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid schedule time format for campaign {pk}: '{scheduled_time_str}' - {e}")
            messages.error(request, "Invalid date/time format provided.")
        except Exception as e:
            logger.error(f"Error scheduling campaign {pk}: {e}")
            messages.error(request, "An error occurred while trying to schedule the campaign.")
    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

@user_passes_test(is_staff_user)
@require_POST
def cancel_campaign(request, pk):
    """ Cancels a campaign that is currently in 'Scheduled' status. """
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    if campaign.status == 'SCHEDULED':
        try:
            with transaction.atomic():
                campaign.status = 'CANCELLED'; campaign.scheduled_time = None
                campaign.save(update_fields=['status', 'scheduled_time'])
            logger.info(f"Scheduled campaign '{campaign.name}' (ID: {pk}) cancelled by user {request.user}.")
            messages.info(request, f"Scheduled campaign '{campaign.name}' has been cancelled.")
        except Exception as e: logger.error(f"Error cancelling campaign {pk}: {e}"); messages.error(request, "An error occurred while trying to cancel the campaign.")
    else: messages.error(request, "Only campaigns with status 'Scheduled' can be cancelled.")
    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)


@user_passes_test(is_staff_user)
@require_POST
def campaign_delete(request, pk):
    """ Deletes a specific marketing campaign. """
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    campaign_name = campaign.name
    try:
        campaign.delete()
        messages.success(request, f"Campaign '{campaign_name}' deleted successfully.")
        logger.info(f"Marketing campaign {pk} ('{campaign_name}') deleted by user {request.user.username}")
    except Exception as e:
        logger.exception(f"Error deleting marketing campaign {pk}: {e}")
        messages.error(request, "An error occurred while deleting the campaign.")
    return redirect('whatsapp_app:campaign_list')

# --- Template Views ---
@user_passes_test(is_staff_user)
def template_list(request):
    """ Displays synced WhatsApp message templates. """
    templates = MarketingTemplate.objects.order_by('name', 'language')
    context = {'templates': templates}
    return render(request, 'whatsapp/marketing/template_list.html', context)


@user_passes_test(is_staff_user)
@require_POST
def sync_whatsapp_templates(request):
    """ Fetches approved templates from WhatsApp API and updates the local DB. """
    synced_count = 0; created_count = 0
    try:
        settings = get_active_whatsapp_settings()
        templates_data = fetch_whatsapp_templates_from_api(settings)
        if templates_data is None: messages.error(request, "Failed to fetch templates from WhatsApp API."); return redirect('whatsapp_app:template_list')
        if not templates_data: messages.info(request, "No approved templates found in your WhatsApp Business Account."); return redirect('whatsapp_app:template_list')
        with transaction.atomic():
            existing_templates = set(MarketingTemplate.objects.values_list('name', 'language')); api_template_keys = set()
            for template_info in templates_data:
                name = template_info.get('name'); language = template_info.get('language'); category = template_info.get('category')
                components = template_info.get('components'); status = template_info.get('status')
                if not all([name, language, category, components, status]) or status != 'APPROVED': continue
                api_template_keys.add((name, language))
                obj, created = MarketingTemplate.objects.update_or_create(
                    name=name, language=language,
                    defaults={'category': category.upper(), 'components': components, 'last_synced': timezone.now()}
                )
                synced_count += 1; created_count += 1 if created else 0
            # Optional deletion of stale templates
            # stale_templates = existing_templates - api_template_keys
            # if stale_templates: MarketingTemplate.objects.filter(name__in=[k[0] for k in stale_templates], language__in=[k[1] for k in stale_templates]).delete()
        if created_count > 0: messages.success(request, f"Template sync complete: Added {created_count} new templates. Updated {synced_count - created_count}.")
        elif synced_count > 0: messages.success(request, f"Template sync complete: Updated {synced_count} existing templates. No new templates found.")
        else: messages.info(request, "Template sync complete: No changes detected.")
    except ValueError as e: logger.error(f"Configuration error during template sync: {e}"); messages.error(request, f"Configuration Error: {e}")
    except Exception as e: logger.exception(f"Unexpected error during WhatsApp template sync: {e}"); messages.error(request, f"An unexpected error occurred during sync: {e}")
    return redirect('whatsapp_app:template_list')

# Added new contact save 
@user_passes_test(is_staff_user)
def add_new_contact(request):
    """Allows staff users to manually add a new WhatsApp contact."""
    if request.method == 'POST':
        form = AddContactForm(request.POST)
        if form.is_valid():
            try:
                contact = form.save()
                messages.success(request, f"Contact '{contact.wa_id}' added successfully.")
                return redirect('whatsapp_app:contact_list')  # Redirect to a contact list view (you might need to create this)
            except Exception as e:
                messages.error(request, f"Error adding contact: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AddContactForm()

    context = {'form': form, 'action': 'Add New Contact'}
    return render(request, 'whatsapp/contact_form.html', context)

# --- Placeholder views removed as actual views are now implemented above ---
# def whatsapp_index(request): ...
# def chat_list(request): ... # Defined above
# def chat_detail(request, wa_id): ... # Defined above
# def template_list(request): ... # Defined above
# def webhook_handler(request): ... # Defined above

