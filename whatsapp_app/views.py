# views.py (within your whatsapp_app)

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
from decimal import Decimal # For handling potential timestamp decimals

# --- App Imports ---
# Models from this app
from .models import (
    Contact, ChatMessage, WhatsAppSettings, BotResponse, AutoReply,
    MarketingTemplate, MarketingCampaign, CampaignContact
)
# Forms from this app
from .forms import (
    WhatsAppSettingsForm, ManualMessageForm, MarketingCampaignForm,
    ContactUploadForm , BotResponseForm, AutoReplySettingsForm # Ensure ManualMessageForm is defined
)
# Utilities from this app (Assume these exist and handle API/parsing logic)
from .utils import (
    send_whatsapp_message, parse_incoming_whatsapp_message,
    fetch_whatsapp_templates_from_api, get_active_whatsapp_settings,
    verify_whatsapp_signature, upload_media_to_whatsapp,
    handle_bot_or_autoreply # Import from utils if needed synchronously (e.g., webhook fallback)
)

# --- Celery (Optional Background Tasks) ---
try:
    # Import the tasks needed by views
    from .tasks import process_whatsapp_webhook_task, send_bulk_campaign_messages_task, send_whatsapp_message_task
    CELERY_ENABLED = True
except ImportError:
    CELERY_ENABLED = False
    # Define dummy task functions if Celery is not installed/enabled
    def process_whatsapp_webhook_task(*args, **kwargs): logger.error("Celery not configured. Cannot run process_whatsapp_webhook_task.")
    def send_whatsapp_message_task(*args, **kwargs): logger.error("Celery not configured. Cannot run send_whatsapp_message_task.")
    def send_bulk_campaign_messages_task(*args, **kwargs): logger.error("Celery not configured. Cannot run send_bulk_campaign_messages_task."); raise NotImplementedError("Celery is not enabled or tasks are not defined.")

# --- Logger Setup ---
logger = logging.getLogger(__name__)

# --- Helper: Check if user is admin/staff ---
def is_staff_user(user):
    """ Checks if the user is authenticated and has staff privileges. """
    return user.is_authenticated and user.is_staff

# ==============================================================================
# Dashboard View
# ==============================================================================
# ... (dashboard view code remains the same) ...
@user_passes_test(is_staff_user)
def dashboard(request):
    today = timezone.now().date(); stats = {}
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
        logger.exception(f"Error fetching dashboard stats: {e}")
        messages.error(request, "Could not load all dashboard statistics.")
        stats.setdefault('total_contacts', 0); stats.setdefault('active_chats_count', 0); stats.setdefault('messages_today', 0)
        stats.setdefault('incoming_today', 0); stats.setdefault('outgoing_today', 0); stats.setdefault('success_rate', 0)
        stats.setdefault('failed_count', 0); stats.setdefault('recent_campaigns', [])
    context = stats
    return render(request, 'whatsapp/dashboard.html', context)

# ==============================================================================
# Settings View
# ==============================================================================
# ... (whatsapp_settings_view code remains the same) ...
@user_passes_test(is_staff_user)
def whatsapp_settings_view(request):
    settings_name = "NurseryProjectDefault"; settings_instance, created = WhatsAppSettings.objects.get_or_create(account_name=settings_name, defaults={'webhook_verify_token': str(uuid.uuid4())})
    if request.method == 'POST':
        form = WhatsAppSettingsForm(request.POST, instance=settings_instance)
        if form.is_valid():
            try: settings = form.save(); messages.success(request, 'WhatsApp API settings saved successfully.'); return redirect('whatsapp_app:settings')
            except Exception as e: logger.exception(f"Error saving WhatsApp settings: {e}"); messages.error(request, f"Failed to save settings: {e}")
        else: messages.error(request, "Please correct the errors highlighted below.")
    else: form = WhatsAppSettingsForm(instance=settings_instance)
    full_webhook_url = None
    if settings_instance:
        try: webhook_path = reverse('whatsapp_app:webhook_handler'); full_webhook_url = request.build_absolute_uri(webhook_path)
        except Exception as e: logger.warning(f"Could not reverse URL for 'whatsapp_app:webhook_handler': {e}")
    context = {'form': form, 'settings': settings_instance, 'full_webhook_url': full_webhook_url}; 
    return render(request, 'whatsapp/settings_form.html', context)

# ==============================================================================
# Webhook Handler (Using Celery Task)
# ==============================================================================
# ... (webhook_handler code remains the same) ...
@csrf_exempt
def webhook_handler(request):
    app_secret = getattr(django_settings, 'WHATSAPP_APP_SECRET', None)
    if app_secret:
        signature = request.headers.get('X-Hub-Signature-256')
        if not signature or not verify_whatsapp_signature(request.body, signature, app_secret): logger.warning("Invalid webhook signature."); return HttpResponseForbidden("Invalid signature.")
    elif not django_settings.DEBUG: logger.warning("WHATSAPP_APP_SECRET not configured. Skipping signature verification.")
    if request.method == 'GET':
        verify_token_param = request.GET.get('hub.verify_token'); challenge = request.GET.get('hub.challenge'); mode = request.GET.get('hub.mode')
        if mode == 'subscribe' and verify_token_param and challenge:
            try: settings = get_active_whatsapp_settings(); expected_token = settings.webhook_verify_token
            if verify_token_param == expected_token: return HttpResponse(challenge, status=200)
            else: logger.warning(f"Webhook verification failed. Token mismatch."); return HttpResponseForbidden("Verification token mismatch.")
            except Exception as e: logger.exception(f"Error during webhook GET verification: {e}"); return HttpResponseForbidden("Internal error during verification.")
        else: logger.warning(f"Invalid GET verification request params."); 
        return HttpResponseBadRequest("Invalid verification request.")
    if request.method == 'POST':
        try:
            raw_body = request.body; payload_str = raw_body.decode('utf-8')
            if not raw_body: logger.warning("Received empty POST body in webhook."); return HttpResponseBadRequest("Empty request body.")
            logger.info(f"Webhook POST received. Queueing processing task.")
            if CELERY_ENABLED: process_whatsapp_webhook_task.delay(payload_str=payload_str)
            else: logger.warning("Celery not enabled. Processing webhook synchronously."); payload = json.loads(payload_str); processed_data = parse_incoming_whatsapp_message(payload) # Process sync
            if processed_data and processed_data.get('type') == 'incoming_message': message_obj = processed_data.get('message_object');
            if message_obj and isinstance(message_obj, ChatMessage): handle_bot_or_autoreply(message_obj) # Call helper
            return HttpResponse(status=200) # Acknowledge immediately
        except json.JSONDecodeError: logger.error("Invalid JSON in webhook POST (before queuing)."); return HttpResponse(status=200)
        except Exception as e: logger.exception(f"Error before queuing webhook task: {e}"); 
        return HttpResponse(status=200)
    return HttpResponse(status=405)

# ==============================================================================
# Chat List & Detail Views
# ==============================================================================
# ... (chat_list view remains the same) ...
@user_passes_test(is_staff_user)
def chat_list(request):
    search_query = request.GET.get('q', '').strip()
    contacts_with_messages = Contact.objects.annotate(last_message_time=Max('messages__timestamp')).filter(last_message_time__isnull=False)
    if search_query: contacts_with_messages = contacts_with_messages.filter(Q(name__icontains=search_query) | Q(wa_id__icontains=search_query))
    contacts = contacts_with_messages.order_by('-last_message_time')
    context = {'contacts': contacts, 'search_query': search_query}
    return render(request, 'whatsapp/chat_list.html', context)

# ... (chat_detail view remains the same) ...
@user_passes_test(is_staff_user)
def chat_detail(request, wa_id):
    contact = get_object_or_404(Contact, wa_id=wa_id)
    messages_qs = ChatMessage.objects.filter(contact=contact).order_by('timestamp')
    form = ManualMessageForm()
    last_msg = messages_qs.last(); last_message_timestamp_iso = last_msg.timestamp.isoformat() if last_msg else timezone.now().isoformat()
    context = {'contact': contact, 'messages': messages_qs, 'form': form, 'last_message_timestamp': last_message_timestamp_iso}
    return render(request, 'whatsapp/chat_detail.html', context)

# ==============================================================================
# AJAX Endpoints for Chat
# ==============================================================================
# ... (send_manual_message_ajax view remains the same) ...
@user_passes_test(is_staff_user)
@require_POST
def send_manual_message_ajax(request):
    wa_id = request.POST.get('wa_id'); form = ManualMessageForm(request.POST)
    if not wa_id: return JsonResponse({'status': 'error', 'message': 'Missing wa_id parameter.'}, status=400)
    contact = get_object_or_404(Contact, wa_id=wa_id)
    if form.is_valid():
        message_text = form.cleaned_data['text_content']
        try:
            if CELERY_ENABLED: send_whatsapp_message_task.delay(recipient_wa_id=contact.wa_id, message_type='text', text_content=message_text); return JsonResponse({'status': 'success', 'message': 'Message queued for sending.'})
            else: logger.warning("Celery not enabled. Sending message synchronously."); message_obj = send_whatsapp_message(recipient_wa_id=contact.wa_id, message_type='text', text_content=message_text);
            if message_obj: return JsonResponse({'status': 'success', 'message': {'message_id': message_obj.message_id, 'text_content': message_obj.text_content, 'timestamp': message_obj.timestamp.isoformat(), 'direction': 'OUT', 'status': message_obj.status, 'message_type': message_obj.message_type, 'template_name': message_obj.template_name, 'media_url': message_obj.media_url,}})
            else: return JsonResponse({'status': 'error', 'message': 'Failed to send message synchronously.'}, status=500)
        except Exception as e: logger.exception(f"Error triggering send task for {wa_id}: {e}"); return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred.'}, status=500)
    else: logger.warning(f"Manual message form validation failed for {wa_id}: {form.errors.as_json()}"); return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

# --- UPDATED get_latest_messages_ajax View ---
@user_passes_test(is_staff_user)
@require_GET
def get_latest_messages_ajax(request):
    """ AJAX endpoint for polling new messages (Fallback if WebSockets fail). """
    wa_id = request.GET.get('wa_id')
    last_timestamp_str = request.GET.get('last_timestamp')

    if not wa_id or not last_timestamp_str:
        return JsonResponse({'status': 'error', 'message': 'Missing required parameters (wa_id, last_timestamp)'}, status=400)

    # --- Log incoming request ---
    logger.info(f"[Poll] Request received for wa_id: {wa_id} after timestamp_str: '{last_timestamp_str}'")

    try:
        contact = Contact.objects.get(wa_id=wa_id)
        # Parse the timestamp provided by the client
        last_timestamp = parse_datetime(last_timestamp_str)
        if not last_timestamp:
            logger.warning(f"[Poll] Invalid timestamp format received from client: {last_timestamp_str}")
            return JsonResponse({'status': 'error', 'message': 'Invalid timestamp format'}, status=400)

        # Ensure it's timezone-aware for comparison
        if timezone.is_naive(last_timestamp):
            last_timestamp = timezone.make_aware(last_timestamp, timezone.get_default_timezone())

        # --- Log the timestamp being used for the query ---
        # Use Decimal for potentially higher precision comparison if needed, though ISO format usually sufficient
        # last_ts_decimal = Decimal(last_timestamp.timestamp())
        logger.info(f"[Poll] Querying messages for {wa_id} with timestamp > {last_timestamp.isoformat()} ({last_timestamp.timestamp()})")

        # Fetch messages strictly newer than the last one the client reported
        # Use system timestamp for reliable ordering
        new_messages_qs = ChatMessage.objects.filter(
            contact=contact,
            timestamp__gt=last_timestamp # Use greater than comparison
        ).order_by('timestamp') # Order by timestamp ascending

        # --- Log the raw query results ---
        found_ids = [msg.message_id for msg in new_messages_qs]
        logger.info(f"[Poll] Found {len(found_ids)} new messages in DB query. IDs: {found_ids}")

        # Select only needed fields for efficiency to send back as JSON
        new_messages_data = list(new_messages_qs.values(
            'message_id', 'text_content', 'timestamp', 'direction', 'status',
            'media_url', 'message_type', 'template_name'
            # Add 'filename' if you added it to the ChatMessage model
        ))

        # Convert datetime objects to ISO strings and find the actual latest timestamp
        latest_ts_in_response = last_timestamp # Initialize with the request timestamp
        for msg_data in new_messages_data:
            # --- Log timestamp before conversion ---
            original_ts = msg_data.get('timestamp')
            logger.debug(f"[Poll] Processing message {msg_data.get('message_id')}, DB timestamp: {original_ts.isoformat() if isinstance(original_ts, timezone.datetime) else original_ts}")

            if isinstance(original_ts, timezone.datetime):
                # Update latest_ts_in_response with the actual latest timestamp found
                if original_ts > latest_ts_in_response:
                     latest_ts_in_response = original_ts
                msg_data['timestamp'] = original_ts.isoformat() # Convert for JSON

        # Determine the timestamp for the *next* poll
        # Use the timestamp of the actual latest message found, or the previous timestamp if none found
        next_poll_timestamp_iso = latest_ts_in_response.isoformat()
        logger.info(f"[Poll] Returning {len(new_messages_data)} messages. Next timestamp for client: {next_poll_timestamp_iso}")
        # logger.debug(f"[Poll] Data being sent: {json.dumps(new_messages_data)}")

        return JsonResponse({
            'status': 'success',
            'new_messages': new_messages_data,
            'next_poll_timestamp': next_poll_timestamp_iso, # Tell client the new 'last_timestamp' to use
        })
    except Contact.DoesNotExist:
        logger.warning(f"[Poll] Contact not found: {wa_id}")
        return JsonResponse({'status': 'error', 'message': 'Contact not found'}, status=404)
    except Exception as e:
        logger.exception(f"[Poll] Error fetching latest messages for {wa_id}: {e}") # Log full traceback
        return JsonResponse({'status': 'error', 'message': 'Server error fetching messages'}, status=500)

# ... (upload_whatsapp_media_ajax view remains the same) ...
@user_passes_test(is_staff_user)
@require_POST
def upload_whatsapp_media_ajax(request):
    if not request.FILES.get('media_file'): return JsonResponse({'status': 'error', 'message': 'No media file found.'}, status=400)
    media_file = request.FILES['media_file']; wa_id = request.POST.get('wa_id')
    max_size = 16 * 1024 * 1024; allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'video/mp4', 'video/3gpp', 'application/pdf'] # Add more
    if media_file.size > max_size: return JsonResponse({'status': 'error', 'message': f'File size exceeds limit ({max_size // 1024 // 1024}MB).'}, status=400)
    if media_file.content_type not in allowed_types: return JsonResponse({'status': 'error', 'message': f'Unsupported file type: {media_file.content_type}.'}, status=400)
    try:
        upload_result = upload_media_to_whatsapp(media_file) # Util handles API call
        if upload_result and upload_result.get('id'): logger.info(f"Uploaded media for {wa_id}, media_id: {upload_result['id']}"); return JsonResponse({'status': 'success', 'media_id': upload_result['id'], 'media_type': upload_result.get('type', 'document')})
        else: logger.error(f"Failed to upload media to WhatsApp API for {wa_id}."); return JsonResponse({'status': 'error', 'message': 'Failed to upload media to WhatsApp.'}, status=500)
    except Exception as e: logger.exception(f"Error during media upload for {wa_id}: {e}"); return JsonResponse({'status': 'error', 'message': 'Server error during media upload.'}, status=500)


# ==============================================================================
# Bot Response CRUD Views
# ==============================================================================
# ... (bot response CRUD views remain the same) ...
@user_passes_test(is_staff_user)
def bot_response_list(request): bot_responses = BotResponse.objects.order_by('trigger_phrase'); context = {'bot_responses': bot_responses}; return render(request, 'whatsapp_app/bot_list.html', context)
@user_passes_test(is_staff_user)
def bot_response_create(request):
    if request.method == 'POST': form = BotResponseForm(request.POST)
    else: form = BotResponseForm()
    if form.is_valid():
        try: bot_response = form.save(); messages.success(request, f"Bot response for '{bot_response.trigger_phrase}' created."); return redirect('whatsapp_app:bot_list')
        except Exception as e: logger.error(f"Error creating bot response: {e}"); messages.error(request, "Error creating response.")
    elif request.method == 'POST': messages.error(request, "Please correct errors.")
    context = {'form': form, 'action': 'Create'}; 
    return render(request, 'whatsapp/bot/bot_response_form.html', context)
@user_passes_test(is_staff_user)
def bot_response_update(request, pk):
    bot_response = get_object_or_404(BotResponse, pk=pk)
    if request.method == 'POST': form = BotResponseForm(request.POST, instance=bot_response)
    else: form = BotResponseForm(instance=bot_response)
    if form.is_valid():
        try: bot_response = form.save(); messages.success(request, f"Bot response for '{bot_response.trigger_phrase}' updated."); return redirect('whatsapp_app:bot_list')
        except Exception as e: logger.error(f"Error updating bot response {pk}: {e}"); messages.error(request, "Error updating response.")
    elif request.method == 'POST': messages.error(request, "Please correct errors.")
    context = {'form': form, 'bot_response': bot_response, 'action': 'Update'}; 
    return render(request, 'whatsapp/bot/bot_response_form.html', context)
@user_passes_test(is_staff_user)
@require_POST
def bot_response_delete(request, pk):
    bot_response = get_object_or_404(BotResponse, pk=pk); trigger_phrase = bot_response.trigger_phrase
    try: bot_response.delete(); messages.success(request, f"Bot response for '{trigger_phrase}' deleted."); logger.info(f"Bot response {pk} deleted by {request.user.username}")
    except Exception as e: logger.error(f"Error deleting bot response {pk}: {e}"); messages.error(request, "Error deleting response.")
    return redirect('whatsapp_app:bot_list')


# ==============================================================================
# Auto-Reply View
# ==============================================================================
# ... (autoreply_settings_view code remains the same) ...
@user_passes_test(is_staff_user)
def autoreply_settings_view(request):
    settings, created = AutoReply.objects.get_or_create(pk=1)
    if request.method == 'POST': form = AutoReplySettingsForm(request.POST, instance=settings)
    else: form = AutoReplySettingsForm(instance=settings)
    if form.is_valid():
        try: settings = form.save(); messages.success(request, "Auto-reply settings updated."); return redirect('whatsapp_app:autoreply_settings')
        except Exception as e: logger.exception(f"Error saving auto-reply: {e}"); messages.error(request, "Error saving settings.")
    elif request.method == 'POST': messages.error(request, "Please correct errors.")
    context = {'form': form, 'settings': settings}; 
    return render(request, 'whatsapp/bot/autoreply_settings.html', context)


# ==============================================================================
# Marketing Campaign Views
# ==============================================================================
# ... (campaign views remain the same) ...
@user_passes_test(is_staff_user)
def campaign_list(request): campaigns = MarketingCampaign.objects.select_related('template').order_by('-created_at'); context = {'campaigns': campaigns}; return render(request, 'whatsapp_app/marketing/campaign_list.html', context)
@user_passes_test(is_staff_user)
def campaign_detail(request, pk):
    campaign = get_object_or_404(MarketingCampaign.objects.select_related('template'), pk=pk); recipients = CampaignContact.objects.filter(campaign=campaign).select_related('contact').order_by('contact__wa_id')
    stats = recipients.aggregate(total=Count('id'), pending=Count('id', filter=Q(status='PENDING')), sent=Count('id', filter=Q(status='SENT')), delivered=Count('id', filter=Q(status='DELIVERED')), read=Count('id', filter=Q(status='READ')), failed=Count('id', filter=Q(status='FAILED')))
    stats['sent_pct'] = 0; stats['delivered_pct'] = 0; stats['read_pct'] = 0; stats['failed_pct'] = 0
    if stats['total'] > 0: processed_total = stats['total'] - stats['pending']; base = processed_total if processed_total > 0 else 1; stats['sent_pct'] = round((stats['sent'] + stats['delivered'] + stats['read'] + stats['failed']) / stats['total'] * 100, 1);
    if base > 0: stats['delivered_pct'] = round((stats['delivered'] + stats['read']) / base * 100, 1); stats['read_pct'] = round(stats['read'] / base * 100, 1); stats['failed_pct'] = round(stats['failed'] / base * 100, 1)
    upload_form = ContactUploadForm() if campaign.status == 'DRAFT' else None
    context = { 'campaign': campaign, 'recipients': recipients, 'stats': stats, 'upload_form': upload_form, 'celery_enabled': CELERY_ENABLED }; return render(request, 'whatsapp_app/marketing/campaign_detail.html', context)
@user_passes_test(is_staff_user)
def campaign_create(request):
    if request.method == 'POST': form = MarketingCampaignForm(request.POST)
    else: form = MarketingCampaignForm()
    if form.is_valid():
        try: campaign = form.save(commit=False); campaign.status = 'DRAFT'; campaign.save(); messages.success(request, f"Campaign '{campaign.name}' created."); return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)
        except Exception as e: logger.error(f"Error creating campaign: {e}"); messages.error(request, "Error creating campaign.")
    elif request.method == 'POST': messages.error(request, "Please correct errors.")
    context = {'form': form, 'action': 'Create'}; 
    return render(request, 'whatsapp/marketing/campaign_form.html', context)
@user_passes_test(is_staff_user)
@require_POST
def upload_contacts_for_campaign(request, pk):
    # ... (upload logic remains the same) ...
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    if campaign.status != 'DRAFT': messages.error(request, "Contacts only for 'Draft' campaigns."); return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)
    form = ContactUploadForm(request.POST, request.FILES)
    if form.is_valid():
        csv_file = request.FILES['contact_file']
        if not csv_file.name.lower().endswith('.csv'): messages.error(request, 'Invalid file type. Use CSV.'); return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)
        added, skipped, invalid = 0, 0, 0; line = 1; to_process = []
        try:
            file_data = csv_file.read().decode('utf-8-sig'); io_string = io.StringIO(file_data); reader = csv.reader(io_string)
            header = next(reader); header_lower = [h.lower().strip() for h in header]
            if 'wa_id' not in header_lower: raise ValueError("CSV needs 'wa_id' column.")
            wa_id_idx = header_lower.index('wa_id'); name_idx = header_lower.index('name') if 'name' in header_lower else -1
            var_map = {}; var_num = 1
            for idx, col in enumerate(header_lower):
                if idx not in [wa_id_idx, name_idx]: var_map[str(var_num)] = idx; var_num += 1
            for row in reader:
                line += 1;
                if not row or len(row) <= wa_id_idx or not row[wa_id_idx].strip(): continue
                wa_id = row[wa_id_idx].strip()
                if not wa_id.isdigit() or not (10 <= len(wa_id) <= 15): invalid += 1; continue
                name = row[name_idx].strip() if name_idx != -1 and len(row) > name_idx else None
                variables = {vn: row[c_idx].strip() if len(row) > c_idx else "" for vn, c_idx in var_map.items()}
                to_process.append({'wa_id': wa_id, 'name': name, 'variables': variables or None})
            if to_process:
                with transaction.atomic():
                    for item in to_process:
                        contact, c_created = Contact.objects.get_or_create(wa_id=item['wa_id'])
                        if item['name'] and (c_created or contact.name != item['name']): contact.name = item['name']; contact.save(update_fields=['name'])
                        _, cc_created = CampaignContact.objects.get_or_create(campaign=campaign, contact=contact, defaults={'template_variables': item['variables']})
                        if cc_created: added += 1
                        else: skipped += 1
            if added > 0: messages.success(request, f"Added {added} new recipients.")
            if skipped > 0: messages.info(request, f"Skipped {skipped} duplicates.")
            if invalid > 0: messages.warning(request, f"Skipped {invalid} invalid 'wa_id' rows.")
            if added + skipped + invalid == 0: messages.info(request, "No valid recipients found.")
        except Exception as e: logger.exception(f"Error processing CSV for campaign {pk}: {e}"); messages.error(request, f"Error processing file: {e}")
    else: # Form invalid
        for field, errors in form.errors.items(): messages.error(request, f"{form.fields[field].label if field!='__all__' else ''}: {'; '.join(errors)}")
    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

@user_passes_test(is_staff_user)
@require_POST
def schedule_campaign(request, pk):
    # ... (schedule logic remains the same) ...
    if not CELERY_ENABLED: messages.error(request, "Celery not enabled."); return redirect('whatsapp_app:campaign_detail', pk=pk)
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    if campaign.status not in ['DRAFT', 'SCHEDULED', 'CANCELLED']: messages.error(request, "Campaign not in schedulable state."); return redirect('whatsapp_app:campaign_detail', pk=pk)
    if not CampaignContact.objects.filter(campaign=campaign).exists(): messages.error(request, "No contacts uploaded."); return redirect('whatsapp_app:campaign_detail', pk=pk)
    scheduled_time_str = request.POST.get('scheduled_time')
    if not scheduled_time_str: # Send now
        try:
            with transaction.atomic(): campaign.scheduled_time = None; campaign.status = 'SENDING'; campaign.started_at = timezone.now(); campaign.completed_at = None; campaign.save(update_fields=['scheduled_time', 'status', 'started_at', 'completed_at']); send_bulk_campaign_messages_task.delay(campaign.id)
            logger.info(f"Campaign '{campaign.name}' queued for immediate sending."); messages.success(request, f"Campaign '{campaign.name}' sending started.")
        except Exception as e: logger.error(f"Error initiating send for campaign {pk}: {e}"); messages.error(request, "Error starting campaign.")
    else: # Schedule later
        try:
            scheduled_time = parse_datetime(scheduled_time_str); default_tz = timezone.get_default_timezone()
            if not scheduled_time: raise ValueError("Invalid format")
            if timezone.is_naive(scheduled_time): scheduled_time = timezone.make_aware(scheduled_time, default_tz)
            else: scheduled_time = scheduled_time.astimezone(default_tz)
            if scheduled_time <= timezone.now(): messages.error(request, "Scheduled time must be in future."); return redirect('whatsapp_app:campaign_detail', pk=pk)
            with transaction.atomic(): campaign.scheduled_time = scheduled_time; campaign.status = 'SCHEDULED'; campaign.started_at = None; campaign.completed_at = None; campaign.save(update_fields=['scheduled_time', 'status', 'started_at', 'completed_at'])
            logger.info(f"Campaign '{campaign.name}' scheduled for {scheduled_time}."); messages.success(request, f"Campaign scheduled for {scheduled_time.strftime('%Y-%m-%d %H:%M %Z')}.")
        except (ValueError, TypeError) as e: logger.warning(f"Invalid schedule time format: '{scheduled_time_str}' - {e}"); messages.error(request, "Invalid date/time format.")
        except Exception as e: logger.error(f"Error scheduling campaign {pk}: {e}"); messages.error(request, "Error scheduling campaign.")
    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)

@user_passes_test(is_staff_user)
@require_POST
def cancel_campaign(request, pk):
    # ... (cancel logic remains the same) ...
    campaign = get_object_or_404(MarketingCampaign, pk=pk)
    if campaign.status == 'SCHEDULED':
        try:
            with transaction.atomic(): campaign.status = 'CANCELLED'; campaign.scheduled_time = None; campaign.save(update_fields=['status', 'scheduled_time'])
            logger.info(f"Scheduled campaign '{campaign.name}' cancelled by {request.user}."); messages.info(request, f"Campaign '{campaign.name}' cancelled.")
        except Exception as e: logger.error(f"Error cancelling campaign {pk}: {e}"); messages.error(request, "Error cancelling campaign.")
    else: messages.error(request, "Only 'Scheduled' campaigns can be cancelled.")
    return redirect('whatsapp_app:campaign_detail', pk=campaign.pk)


@user_passes_test(is_staff_user)
@require_POST
def campaign_delete(request, pk):
    """ Deletes a specific marketing campaign. """
    # ... (delete logic remains the same) ...
    campaign = get_object_or_404(MarketingCampaign, pk=pk); campaign_name = campaign.name
    try: campaign.delete(); messages.success(request, f"Campaign '{campaign_name}' deleted."); logger.info(f"Campaign {pk} deleted by {request.user.username}")
    except Exception as e: logger.exception(f"Error deleting campaign {pk}: {e}"); messages.error(request, "Error deleting campaign.")
    return redirect('whatsapp_app:campaign_list')

# --- Template Views ---
@user_passes_test(is_staff_user)
def template_list(request):
    """ Displays synced WhatsApp message templates. """
    # ... (template list logic remains the same) ...
    templates = MarketingTemplate.objects.order_by('name', 'language'); 
    context = {'templates': templates}; 
    return render(request, 'whatsapp/marketing/template_list.html', context)


@user_passes_test(is_staff_user)
@require_POST
def sync_whatsapp_templates(request):
    """ Fetches approved templates from WhatsApp API and updates the local DB. """
    # ... (sync templates logic remains the same) ...
    synced, created_c = 0, 0
    try:
        settings = get_active_whatsapp_settings(); templates_data = fetch_whatsapp_templates_from_api(settings)
        if templates_data is None: messages.error(request, "Failed to fetch templates from API."); return redirect('whatsapp_app:template_list')
        if not templates_data: messages.info(request, "No approved templates found in Meta account."); return redirect('whatsapp_app:template_list')
        with transaction.atomic():
            existing = set(MarketingTemplate.objects.values_list('name', 'language')); api_keys = set()
            for t_info in templates_data:
                name=t_info.get('name'); lang=t_info.get('language'); cat=t_info.get('category'); comp=t_info.get('components'); status=t_info.get('status')
                if not all([name, lang, cat, comp, status]) or status != 'APPROVED': continue
                api_keys.add((name, lang))
                obj, created = MarketingTemplate.objects.update_or_create(name=name, language=lang, defaults={'category': cat.upper(), 'components': comp, 'last_synced': timezone.now()})
                synced += 1; created_c += 1 if created else 0
        if created_c > 0: messages.success(request, f"Sync complete: Added {created_c} new templates. Updated {synced - created_c}.")
        elif synced > 0: messages.success(request, f"Sync complete: Updated {synced} templates. None new.")
        else: messages.info(request, "Sync complete: No changes.")
    except ValueError as e: logger.error(f"Config error during sync: {e}"); messages.error(request, f"Config Error: {e}")
    except Exception as e: logger.exception(f"Error during sync: {e}"); messages.error(request, f"Error during sync: {e}")
    return redirect('whatsapp_app:template_list')
