# whatsapp_app/utils.py

import requests
import json
import logging
import hmac # For webhook signature verification
import hashlib # For webhook signature verification
from datetime import datetime, timezone as dt_timezone # Import timezone from datetime
from django.utils import timezone # Keep Django's timezone for other uses like timezone.now()
from django.conf import settings as django_settings # For project level settings like WA_APP_SECRET
from django.core.files.uploadedfile import UploadedFile # For type hinting
from typing import Tuple, Optional # For type hinting
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

# Import models from the *same app*
try:
    # Make sure all necessary models are imported here
    from .models import WhatsAppSettings, Contact, ChatMessage, BotResponse, AutoReply, CampaignContact
except ImportError as e:
     logging.error(f"Could not import models in utils.py: {e}. Check app structure and INSTALLED_APPS.")
     WhatsAppSettings, Contact, ChatMessage, BotResponse, AutoReply, CampaignContact = None, None, None, None, None, None

logger = logging.getLogger(__name__)

# --- Constants ---
WHATSAPP_API_VERSION = getattr(django_settings, "WHATSAPP_API_VERSION", "v19.0")
GRAPH_API_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"

# --- Helper Function to Get Active Settings ---
def get_active_whatsapp_settings() -> WhatsAppSettings:
    """ Retrieves the currently active WhatsApp settings. """
    if WhatsAppSettings is None: raise ImportError("WhatsAppSettings model could not be imported.")
    settings_obj = WhatsAppSettings.objects.first()
    if not settings_obj:
        logger.error("WhatsApp settings not found in database.")
        raise WhatsAppSettings.DoesNotExist("WhatsApp settings have not been configured in the admin.")
    if not settings_obj.whatsapp_token or not settings_obj.phone_number_id:
        logger.error(f"WhatsApp settings '{settings_obj.account_name}' are incomplete (missing Token or Phone ID).")
        raise ValueError(f"WhatsApp settings '{settings_obj.account_name}' are incomplete.")
    return settings_obj

# --- Sending Messages ---
def send_whatsapp_message(recipient_wa_id: str, message_type: str, **kwargs) -> ChatMessage | None:
    """ Sends a message via the WhatsApp Cloud API and logs it in ChatMessage. """
    # --- (Code for send_whatsapp_message remains the same) ---
    if ChatMessage is None or Contact is None: logger.error("Cannot send message: Contact or ChatMessage model not imported."); return None
    try:
        settings = get_active_whatsapp_settings(); api_url = f"{GRAPH_API_URL}/{settings.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {settings.whatsapp_token}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": recipient_wa_id, "type": message_type}
        log_content = None; media_url_to_log = None; template_name_to_log = None
        if message_type == 'text':
            text_content = kwargs.get('text_content'); payload['text'] = {"preview_url": False, "body": text_content}; log_content = text_content
        elif message_type == 'template':
            template_name = kwargs.get('template_name'); template_language = kwargs.get('template_language', 'en'); template_components = kwargs.get('template_components')
            if not all([template_name, template_language, template_components]): raise ValueError("Missing template parameters")
            payload['template'] = {"name": template_name, "language": {"code": template_language}, "components": template_components}
            template_name_to_log = template_name; log_content = f"Template: {template_name}"
        elif message_type in ['image', 'audio', 'video', 'document', 'sticker']:
             link = kwargs.get('media_link'); media_id = kwargs.get('media_id'); caption = kwargs.get('text_content'); filename = kwargs.get('filename')
             if not link and not media_id: raise ValueError(f"Missing media_link/media_id for {message_type}")
             payload[message_type] = {"link": link} if link else {"id": media_id}
             if caption and message_type in ['image', 'video', 'document']: payload[message_type]['caption'] = caption
             if filename and message_type == 'document': payload[message_type]['filename'] = filename
             log_content = caption or f"Sent {message_type}"; media_url_to_log = link if link else None
        else: raise NotImplementedError(f"Message type '{message_type}' sending not implemented.")
        logger.info(f"Attempting to send {message_type} message to {recipient_wa_id}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30); response.raise_for_status()
        response_data = response.json(); message_wamid = response_data.get("messages", [{}])[0].get("id")
        if not message_wamid: logger.error(f"API call ok but no WAMID. Response: {response_data}"); log_failed_message(recipient_wa_id, message_type, "API did not return WAMID", log_content, media_url_to_log, **kwargs); return None
        contact, _ = Contact.objects.get_or_create(wa_id=recipient_wa_id)
        message = ChatMessage.objects.create(message_id=message_wamid, contact=contact, direction='OUT', status='SENT', message_type=message_type, text_content=log_content, media_url=media_url_to_log, template_name=template_name_to_log, timestamp=timezone.now())
        logger.info(f"Message sent via API to {recipient_wa_id}. WAMID: {message_wamid}")
        return message
    except requests.exceptions.RequestException as e: error_message = f"HTTP Error: {e}. Response: {e.response.text if e.response else 'N/A'}"; logger.error(f"Error sending to {recipient_wa_id}: {error_message}"); log_failed_message(recipient_wa_id, message_type, error_message, log_content, media_url_to_log, **kwargs); return None
    except (ValueError, NotImplementedError, KeyError) as e: logger.error(f"Error preparing message for {recipient_wa_id}: {e}"); return None
    except WhatsAppSettings.DoesNotExist as e: logger.error(f"Cannot send message: {e}"); return None
    except Exception as e: error_message = f"Unexpected Error: {e}"; logger.exception(f"Unexpected error sending to {recipient_wa_id}: {e}"); log_failed_message(recipient_wa_id, message_type, error_message, log_content, media_url_to_log, **kwargs); return None

# --- Helper to Log Failed Outgoing Messages ---
def log_failed_message(recipient_wa_id: str, message_type: str, error_details: str,
                       log_content: str | None = None, media_url: str | None = None, **kwargs):
    """ Creates a ChatMessage entry with FAILED status. """
    # --- (Code for log_failed_message remains the same) ---
    if ChatMessage is None or Contact is None: logger.error("Cannot log failed message: Models not imported."); return
    try:
        contact, _ = Contact.objects.get_or_create(wa_id=recipient_wa_id)
        temp_id = f"failed_{timezone.now().strftime('%Y%m%d%H%M%S%f')}_{contact.pk}"
        ChatMessage.objects.create(
            message_id=temp_id[:100], contact=contact, direction='OUT', status='FAILED',
            message_type=message_type, text_content=log_content, media_url=media_url,
            template_name=kwargs.get('template_name') if message_type == 'template' else None,
            timestamp=timezone.now(), error_message=str(error_details)[:500]
        )
        logger.info(f"Logged failed message attempt to {recipient_wa_id}. Temp ID: {temp_id}")
    except Exception as log_err: logger.error(f"!!! Critical: Failed to log a FAILED message attempt to {recipient_wa_id}: {log_err}")


# --- Handling Incoming Webhooks ---
def parse_incoming_whatsapp_message(payload: dict) -> dict | None:
    """
    Parses the incoming webhook payload from WhatsApp.
    Updates or creates Contact and ChatMessage objects.
    Handles different notification types (messages, status updates).
    """
    if ChatMessage is None or Contact is None: logger.error("Cannot parse incoming: Models not imported."); return None
    logger.debug(f"Parsing webhook payload: {json.dumps(payload, indent=2)}")
    if not payload or payload.get("object") != "whatsapp_business_account": logger.warning("Invalid webhook payload."); return None
    processed_info = None; media_id_from_payload = None
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "messages":
                value = change.get("value", {}); metadata = value.get("metadata", {}); contacts_data = value.get("contacts", [])
                messages_data = value.get("messages", []); statuses_data = value.get("statuses", [])
                if messages_data: # Handle Incoming Messages
                    for msg_data in messages_data:
                        try:
                            sender_wa_id = msg_data.get("from"); message_id = msg_data.get("id"); timestamp_ms_str = msg_data.get("timestamp"); msg_type = msg_data.get("type")
                            if not all([sender_wa_id, message_id, msg_type, timestamp_ms_str]): logger.warning(f"Skipping incomplete message data: {msg_data}"); continue
                            if ChatMessage.objects.filter(message_id=message_id).exists(): logger.info(f"Message {message_id} already processed."); continue
                            profile_name = next((c.get("profile", {}).get("name") for c in contacts_data if c.get("wa_id") == sender_wa_id), None)
                            contact, created = Contact.objects.update_or_create(wa_id=sender_wa_id, defaults={'name': profile_name} if profile_name else {})
                            if created: logger.info(f"Created contact: {sender_wa_id} ({profile_name})")
                            elif profile_name and contact.name != profile_name: contact.name = profile_name; contact.save(update_fields=['name']); logger.info(f"Updated contact name: {sender_wa_id}")
                            text_content = None; media_url = None; filename = None; media_id_from_payload = None # Reset for each message
                            if msg_type == 'text': text_content = msg_data.get("text", {}).get("body")
                            elif msg_type == 'reaction': reaction = msg_data.get('reaction', {}); reacted_msg_id = reaction.get('message_id'); text_content = f"Reacted '{reaction.get('emoji', '?')}' to {reacted_msg_id}"
                            elif msg_type in ['image', 'video', 'audio', 'document', 'sticker']: media_info = msg_data.get(msg_type, {}); media_id_from_payload = media_info.get('id'); caption = media_info.get('caption'); filename = media_info.get('filename'); text_content = caption or f"Received {msg_type}"; logger.info(f"Received {msg_type} media ID {media_id_from_payload}");
                            elif msg_type == 'location': loc = msg_data.get('location', {}); text_content = f"Location: Lat {loc.get('latitude')}, Lon {loc.get('longitude')}"; text_content += f" ({loc.get('name')})" if loc.get('name') else ""
                            elif msg_type == 'contacts': contacts_shared = msg_data.get('contacts', []); names = [c.get('name', {}).get('formatted_name', 'Unknown') for c in contacts_shared]; text_content = f"Shared contact(s): {', '.join(names)}"
                            elif msg_type == 'interactive': interactive_data = msg_data.get('interactive', {}); interactive_type = interactive_data.get('type'); reply_info = interactive_data.get('button_reply' if interactive_type == 'button_reply' else 'list_reply', {}); text_content = f"{interactive_type.replace('_',' ').title()}: '{reply_info.get('title')}' (ID: {reply_info.get('id')})"
                            elif msg_type == 'unsupported': text_content = "Received an unsupported message type."
                            else: text_content = f"Received unhandled message type: {msg_type}"; logger.warning(f"Unhandled type '{msg_type}': {msg_data}")

                            # --- CORRECTED: Try/Except block for timestamp parsing ---
                            whatsapp_dt = None
                            try:
                                # Use datetime.timezone.utc (imported as dt_timezone.utc)
                                whatsapp_dt = datetime.fromtimestamp(int(timestamp_ms_str), tz=dt_timezone.utc)
                            except (ValueError, TypeError):
                                logger.warning(f"Could not parse WhatsApp timestamp: {timestamp_ms_str}")
                            # --- End Correction ---

                            message = ChatMessage.objects.create(
                                message_id=message_id, contact=contact, direction='IN', status='RECEIVED',
                                message_type=msg_type, text_content=text_content, media_url=media_url,
                                timestamp=timezone.now(), whatsapp_timestamp=whatsapp_dt
                                # NOTE: media_id is NOT saved here by default
                            )
                            # Store media_id temporarily on object if present, for task to use
                            if media_id_from_payload: message.media_id_from_payload = media_id_from_payload
                            logger.info(f"Processed incoming {msg_type} message {message_id} from {sender_wa_id}")
                            if not processed_info: processed_info = {'type': 'incoming_message', 'message_object': message}
                        except Exception as msg_proc_err: logger.exception(f"Error processing one incoming message: {msg_proc_err}. Data: {msg_data}")
                elif statuses_data: # Handle Status Updates
                    for status_data in statuses_data:
                        try:
                            message_wamid = status_data.get("id"); status = status_data.get("status"); recipient_id = status_data.get("recipient_id")
                            if not all([message_wamid, status, recipient_id]): logger.warning(f"Skipping incomplete status update: {status_data}"); continue
                            try: message = ChatMessage.objects.get(message_id=message_wamid, direction='OUT')
                            except ChatMessage.DoesNotExist: logger.warning(f"Status update for unknown WAMID: {message_wamid}"); continue
                            new_status_map = {'sent': 'SENT', 'delivered': 'DELIVERED', 'read': 'READ', 'failed': 'FAILED'}; new_status = new_status_map.get(status.lower())
                            if new_status and message.status != new_status: # Simple update logic
                                message.status = new_status; update_fields = ['status']
                                if new_status == 'FAILED' and status_data.get("errors"): message.error_message = json.dumps(status_data["errors"]); update_fields.append('error_message')
                                message.save(update_fields=update_fields); logger.info(f"Updated status for {message_wamid} to {new_status}")
                                try: # Update campaign contact status
                                    if CampaignContact: updated_count = CampaignContact.objects.filter(message_id=message_wamid).update(status=new_status);
                                    if updated_count > 0: logger.info(f"Updated CampaignContact status for {message_wamid} to {new_status}")
                                except Exception as cc_update_err: logger.error(f"Error updating CampaignContact status for {message_wamid}: {cc_update_err}")
                                if not processed_info: processed_info = {'type': 'status_update', 'status_data': {'message_id': message_wamid, 'status': new_status, 'wa_id': recipient_id}}
                            elif not new_status: logger.warning(f"Unknown status type '{status}' for {message_wamid}")
                        except Exception as status_proc_err: logger.exception(f"Error processing one status update: {status_proc_err}. Data: {status_data}")
                elif value.get("errors"): logger.error(f"Received errors object in webhook: {value['errors']}")
            elif change.get("field"): logger.debug(f"Ignoring non-messages change field: {change.get('field')}")
    return processed_info


# --- Fetching Templates ---
def fetch_whatsapp_templates_from_api(settings: WhatsAppSettings) -> list | None:
    """ Fetches approved message templates from the WhatsApp Cloud API. """
    # --- (Code for fetch_whatsapp_templates_from_api remains the same) ---
    if not settings.whatsapp_business_account_id: raise ValueError("WhatsApp Business Account ID not configured.")
    api_url = f"{GRAPH_API_URL}/{settings.whatsapp_business_account_id}/message_templates"
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    params = {"fields": "name,status,category,language,components,quality_score", "limit": 100}
    all_templates = []; page_count = 0
    try:
        logger.info(f"Fetching message templates for WABA ID: {settings.whatsapp_business_account_id}")
        while api_url:
            page_count += 1; logger.debug(f"Fetching template page {page_count} from {api_url}")
            current_params = params if page_count == 1 else None
            response = requests.get(api_url, headers=headers, params=current_params, timeout=30)
            response.raise_for_status(); data = response.json()
            all_templates.extend(data.get("data", [])); api_url = data.get("paging", {}).get("next")
            if not api_url: logger.debug("No more template pages found.")
        approved_templates = [t for t in all_templates if t.get('status') == 'APPROVED']
        logger.info(f"Fetched {len(all_templates)} total templates, {len(approved_templates)} are APPROVED.")
        return approved_templates
    except requests.exceptions.RequestException as e: logger.error(f"HTTP Error fetching templates: {e}. Response: {e.response.text if e.response else 'N/A'}"); return None
    except Exception as e: logger.exception(f"Unexpected error fetching templates: {e}"); return None


# --- Optional: Webhook Signature Verification ---
def verify_whatsapp_signature(payload: bytes, signature: str | None, secret: str | None) -> bool:
    """ Verifies the X-Hub-Signature-256 header from WhatsApp webhooks. """
    # --- (Code for verify_whatsapp_signature remains the same) ---
    if not signature or not secret: logger.warning("Cannot verify webhook signature: Missing signature header or App Secret."); return False
    try:
        if not signature.startswith('sha256='): logger.warning(f"Invalid signature format: {signature}"); return False
        expected_hash = signature[len('sha256='):]; byte_secret = secret.encode('utf-8')
        calculated_hash_obj = hmac.new(byte_secret, payload, hashlib.sha256); calculated_hash = calculated_hash_obj.hexdigest()
        is_valid = hmac.compare_digest(expected_hash, calculated_hash)
        if not is_valid: logger.warning(f"Webhook signature mismatch. Header: {expected_hash}, Calculated: {calculated_hash}")
        else: logger.debug("Webhook signature verified successfully.")
        return is_valid
    except Exception as e: logger.error(f"Error during webhook signature verification: {e}"); return False


# --- Media Download Utility ---
def download_whatsapp_media(media_id: str) -> Optional[Tuple[bytes, str]]:
    """ Downloads media file associated with the given media ID from WhatsApp. """
    # --- (Code for download_whatsapp_media remains the same) ---
    if not media_id: logger.warning("Download attempted with no media ID."); return None
    try:
        settings = get_active_whatsapp_settings(); headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
        media_info_url = f"{GRAPH_API_URL}/{media_id}"; logger.debug(f"Fetching media info from: {media_info_url}")
        info_response = requests.get(media_info_url, headers=headers, timeout=15); info_response.raise_for_status()
        media_info = info_response.json(); download_url = media_info.get('url')
        if not download_url: logger.error(f"Could not retrieve download URL for media ID {media_id}. Response: {media_info}"); return None
        logger.debug(f"Retrieved temporary download URL: {download_url}")
        media_response = requests.get(download_url, timeout=60); media_response.raise_for_status()
        content_type = media_response.headers.get('content-type', 'application/octet-stream'); media_content = media_response.content
        logger.info(f"Successfully downloaded media ID {media_id} ({content_type}, {len(media_content)} bytes).")
        return media_content, content_type
    except requests.exceptions.RequestException as e: logger.error(f"HTTP Error downloading media ID {media_id}: {e}. Response: {e.response.text if e.response else 'N/A'}"); return None
    except WhatsAppSettings.DoesNotExist as e: logger.error(f"Cannot download media: {e}"); return None
    except Exception as e: logger.exception(f"Unexpected error downloading media ID {media_id}: {e}"); return None


# --- Media Upload Utility ---
def upload_media_to_whatsapp(media_file: UploadedFile) -> dict | None:
    """ Uploads a media file to WhatsApp using the /media endpoint to get a reusable ID. """
    # --- (Code for upload_media_to_whatsapp remains the same) ---
    try:
        settings = get_active_whatsapp_settings(); api_url = f"{GRAPH_API_URL}/{settings.phone_number_id}/media"
        headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
        files = {'file': (media_file.name, media_file, media_file.content_type)}
        payload = {'messaging_product': 'whatsapp', 'type': media_file.content_type}
        logger.info(f"Attempting to upload media file '{media_file.name}' ({media_file.content_type}) to WhatsApp.")
        response = requests.post(api_url, headers=headers, data=payload, files=files, timeout=60)
        response.raise_for_status(); response_data = response.json(); media_id = response_data.get('id')
        if media_id:
            logger.info(f"Media uploaded successfully. Media ID: {media_id}")
            content_type = media_file.content_type.lower(); media_type = 'document'
            if content_type.startswith('image/'): media_type = 'image'
            elif content_type.startswith('video/'): media_type = 'video'
            elif content_type.startswith('audio/'): media_type = 'audio'
            return {'id': media_id, 'type': media_type}
        else: logger.error(f"WhatsApp media upload API call successful but did not return a media ID. Response: {response_data}"); return None
    except requests.exceptions.RequestException as e: logger.error(f"HTTP Error uploading media: {e}. Response: {e.response.text if e.response else 'N/A'}"); return None
    except WhatsAppSettings.DoesNotExist as e: logger.error(f"Cannot upload media: {e}"); return None
    except Exception as e: logger.exception(f"Unexpected error uploading media file {media_file.name}: {e}"); return None


# --- Helper Function for Bots/Auto-Replies (Moved from views.py) ---
def handle_bot_or_autoreply(incoming_message: ChatMessage):
    """ Checks and sends bot responses or auto-replies based on incoming message. """
    # --- (Code for handle_bot_or_autoreply remains the same) ---
    if BotResponse is None or AutoReply is None: logger.error("Cannot handle bot/autoreply: Models not imported."); return
    if not incoming_message or not incoming_message.text_content or incoming_message.direction != 'IN': return
    contact = incoming_message.contact; message_text_lower = incoming_message.text_content.lower().strip(); bot_responded = False
    try: # Check Bot Triggers
        bot_response = BotResponse.objects.filter(is_active=True, trigger_phrase__iexact=message_text_lower).first()
        if bot_response:
            last_out_msg = ChatMessage.objects.filter(contact=contact, direction='OUT').order_by('-timestamp').first()
            if not last_out_msg or last_out_msg.text_content != bot_response.response_text:
                send_whatsapp_message(recipient_wa_id=contact.wa_id, message_type='text', text_content=bot_response.response_text)
                logger.info(f"Sent bot response for '{bot_response.trigger_phrase}' to {contact.wa_id}"); bot_responded = True
            else: logger.info(f"Skipping bot response loop for '{bot_response.trigger_phrase}' to {contact.wa_id}"); bot_responded = True
    except Exception as e: logger.exception(f"Error checking/sending bot response for {contact.wa_id}: {e}")
    if not bot_responded: # Check Auto-Reply
        agent_available = False # <<<--- IMPLEMENT YOUR AVAILABILITY LOGIC HERE --- >>>
        if not agent_available:
            try:
                auto_reply_settings = AutoReply.objects.get(pk=1, is_active=True)
                last_out_msg = ChatMessage.objects.filter(contact=contact, direction='OUT').order_by('-timestamp').first()
                if not last_out_msg or last_out_msg.text_content != auto_reply_settings.message_text:
                    send_whatsapp_message(recipient_wa_id=contact.wa_id, message_type='text', text_content=auto_reply_settings.message_text)
                    logger.info(f"Sent auto-reply to {contact.wa_id}")
                else: logger.info(f"Skipping auto-reply loop to {contact.wa_id}")
            except AutoReply.DoesNotExist: logger.info("Auto-reply inactive or not configured.")
            except Exception as e: logger.exception(f"Error checking/sending auto-reply for {contact.wa_id}: {e}")

