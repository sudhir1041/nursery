# whatsapp_app/utils.py

import requests
import json
import logging
import hmac # For webhook signature verification
import hashlib # For webhook signature verification
from datetime import datetime
from django.utils import timezone
from django.conf import settings as django_settings # For project level settings like WA_APP_SECRET

# Import models from the *same app*
from .models import WhatsAppSettings, Contact, ChatMessage

# Potentially import models from other apps if needed for context during sending/parsing
# from orders.models import Order # Example
# from marketing.models import CampaignContact # Example for status updates

logger = logging.getLogger(__name__) # Use logger defined in settings.py

# --- Constants ---
# Consider moving these to settings.py if they might change
WHATSAPP_API_VERSION = "v19.0" # Use a recent, supported version
GRAPH_API_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"

# --- Helper Function to Get Active Settings ---
def get_active_whatsapp_settings() -> WhatsAppSettings:
    """
    Retrieves the currently active WhatsApp settings.

    Raises:
        WhatsAppSettings.DoesNotExist: If no settings object is found.
        ValueError: If the found settings are incomplete (missing token or phone ID).

    Returns:
        The active WhatsAppSettings object.
    """
    # Fetch the first settings object found. Adjust filter if you have multiple.
    # Using .first() might hide errors if multiple exist; consider .get() with a specific filter.
    settings = WhatsAppSettings.objects.first()
    if not settings:
        logger.error("WhatsApp settings not found in database.")
        raise WhatsAppSettings.DoesNotExist("WhatsApp settings have not been configured in the admin.")
    if not settings.whatsapp_token or not settings.phone_number_id:
        logger.error(f"WhatsApp settings '{settings.account_name}' are incomplete (missing Token or Phone ID).")
        raise ValueError(f"WhatsApp settings '{settings.account_name}' are incomplete.")
    return settings

# --- Sending Messages ---
def send_whatsapp_message(recipient_wa_id: str, message_type: str, **kwargs) -> ChatMessage | None:
    """
    Sends a message via the WhatsApp Cloud API and logs it in ChatMessage.

    Handles various message types and logs the attempt.

    Args:
        recipient_wa_id: The recipient's WhatsApp ID (phone number with country code).
        message_type: 'text', 'template', 'image', 'document', 'audio', 'video', 'sticker'.
        **kwargs: Additional arguments based on message_type:
            - text_content (for type='text')
            - template_name, template_language, template_components (for type='template')
            - media_id or media_link (for media types)
            - related_order_id (Example custom kwarg for linking logs)

    Returns:
        The created ChatMessage object (with SENT status if API call succeeds initially)
        or None if the API call fails or input is invalid.
        Actual delivery status relies on webhooks.
    """
    try:
        settings = get_active_whatsapp_settings() # Fetch credentials
        api_url = f"{GRAPH_API_URL}/{settings.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {settings.whatsapp_token}",
            "Content-Type": "application/json",
        }

        # --- Construct Base Payload ---
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_wa_id,
            "type": message_type,
        }

        # --- Add Type-Specific Payload Data ---
        log_content = None # For storing simplified content in ChatMessage
        media_url_to_log = None # For storing media link in ChatMessage

        if message_type == 'text':
            text_content = kwargs.get('text_content')
            if not text_content:
                raise ValueError("Missing 'text_content' for text message")
            payload['text'] = {"preview_url": False, "body": text_content}
            log_content = text_content

        elif message_type == 'template':
            template_name = kwargs.get('template_name')
            template_language = kwargs.get('template_language')
            template_components = kwargs.get('template_components') # Should be pre-constructed list/dict
            if not all([template_name, template_language, template_components]):
                 raise ValueError("Missing required template parameters (name, language, components)")
            payload['template'] = {
                "name": template_name,
                "language": {"code": template_language},
                "components": template_components,
            }
            # Log the template name and maybe variables for context
            log_content = f"Template: {template_name}" # Variables logged in CampaignContact

        elif message_type in ['image', 'audio', 'video', 'document', 'sticker']:
             # Media messages require either a public URL (link) or an uploaded media ID
             link = kwargs.get('media_link')
             media_id = kwargs.get('media_id')
             caption = kwargs.get('caption') # Optional caption for some media types

             if not link and not media_id:
                 raise ValueError(f"Missing 'media_link' or 'media_id' for {message_type} message")

             payload[message_type] = {"link": link} if link else {"id": media_id}
             if caption and message_type in ['image', 'video', 'document']: # Check API docs for caption support
                  payload[message_type]['caption'] = caption

             log_content = f"{message_type.capitalize()}: {link or media_id}"
             if link: media_url_to_log = link # Log the public link if provided

        # Add elif blocks for other message types (interactive, location, contacts) here...
        else:
            raise NotImplementedError(f"Message type '{message_type}' sending not implemented in utils.py.")

        # --- Make API Call ---
        logger.info(f"Attempting to send {message_type} message to {recipient_wa_id}")
        logger.debug(f"API URL: {api_url}")
        logger.debug(f"Payload: {json.dumps(payload)}")

        response = requests.post(api_url, headers=headers, json=payload, timeout=30) # Set timeout

        # Check for HTTP errors (4xx, 5xx)
        response.raise_for_status()

        response_data = response.json()
        logger.debug(f"API Response: {response_data}")

        # --- Process API Response ---
        # Extract the WhatsApp Message ID (WAMID)
        message_wamid = response_data.get("messages", [{}])[0].get("id")

        if not message_wamid:
            logger.error(f"WhatsApp API call successful but did not return a message ID (WAMID). Response: {response_data}")
            # Decide how to handle this - log as failed? Return None?
            # It's unusual but possible. We'll log as failed for now.
            log_failed_message(recipient_wa_id, message_type, "API did not return WAMID", log_content, media_url_to_log, **kwargs)
            return None

        # --- Log the outgoing message in DB (Success Case) ---
        contact, _ = Contact.objects.get_or_create(wa_id=recipient_wa_id)

        # ***** Integration Point *****
        # Fetch related nursery project objects if IDs were passed in kwargs
        # related_order = None
        # related_order_id = kwargs.get('related_order_id')
        # if related_order_id:
        #     try:
        #         related_order = Order.objects.get(id=related_order_id)
        #     except Order.DoesNotExist:
        #         logger.warning(f"Order ID {related_order_id} not found when logging WhatsApp message {message_wamid}")

        # Create the message log with 'SENT' status (API accepted it)
        message = ChatMessage.objects.create(
            message_id=message_wamid, # Use WAMID from response as PK
            contact=contact,
            direction='OUT',
            status='SENT', # Mark as SENT because API accepted it and gave WAMID
            message_type=message_type,
            text_content=log_content, # Store simplified content/description
            media_url=media_url_to_log, # Store public media URL if used
            template_name=kwargs.get('template_name') if message_type == 'template' else None,
            timestamp=timezone.now(), # Log when we sent it
            # related_order=related_order, # Assign linked object
        )
        logger.info(f"Message successfully sent via API to {recipient_wa_id}. WAMID: {message_wamid}")
        return message

    # --- Error Handling ---
    except requests.exceptions.RequestException as e:
        # Network errors, timeouts, DNS errors, HTTP errors (handled by raise_for_status)
        error_message = f"HTTP Error: {e}. Response: {e.response.text if e.response else 'N/A'}"
        logger.error(f"Error sending message to {recipient_wa_id}: {error_message}")
        log_failed_message(recipient_wa_id, message_type, error_message, log_content, media_url_to_log, **kwargs)
        return None
    except (ValueError, NotImplementedError, KeyError) as e:
        # Errors in preparing the data before sending
        error_message = f"Data/Input Error: {e}"
        logger.error(f"Error preparing message for {recipient_wa_id}: {error_message}")
        # Don't usually log a failed message here as it didn't even reach the API attempt
        return None
    except WhatsAppSettings.DoesNotExist as e:
        logger.error(f"Cannot send message: {e}") # Error logged in get_active_whatsapp_settings
        return None
    except Exception as e:
        # Catch-all for unexpected errors
        error_message = f"Unexpected Error: {e}"
        logger.exception(f"Unexpected error sending message to {recipient_wa_id}: {e}") # Log full traceback
        log_failed_message(recipient_wa_id, message_type, error_message, log_content, media_url_to_log, **kwargs)
        return None

# --- Helper to Log Failed Outgoing Messages ---
def log_failed_message(recipient_wa_id: str, message_type: str, error_details: str,
                       log_content: str | None = None, media_url: str | None = None, **kwargs):
    """Creates a ChatMessage entry with FAILED status."""
    try:
        contact, _ = Contact.objects.get_or_create(wa_id=recipient_wa_id)
        # Generate a temporary unique ID since we don't have a WAMID
        # Using timestamp and contact ID for some uniqueness, but not guaranteed globally
        temp_id = f"failed_{timezone.now().strftime('%Y%m%d%H%M%S%f')}_{contact.pk}"

        ChatMessage.objects.create(
            message_id=temp_id[:100], # Ensure it fits in the field
            contact=contact,
            direction='OUT',
            status='FAILED',
            message_type=message_type,
            text_content=log_content,
            media_url=media_url,
            template_name=kwargs.get('template_name') if message_type == 'template' else None,
            timestamp=timezone.now(),
            error_message=str(error_details)[:500] # Truncate error if needed
        )
        logger.info(f"Logged failed message attempt to {recipient_wa_id}. Temp ID: {temp_id}")
    except Exception as log_err:
        logger.error(f"!!! Critical: Failed to log a FAILED message attempt to {recipient_wa_id}: {log_err}")


# --- Handling Incoming Webhooks ---
def parse_incoming_whatsapp_message(payload: dict) -> dict | None:
    """
    Parses the incoming webhook payload from WhatsApp.
    Updates or creates Contact and ChatMessage objects.
    Handles different notification types (messages, status updates).

    Args:
        payload: The JSON payload dictionary received from WhatsApp.

    Returns:
        A dictionary containing information about the processed event
        (e.g., {'type': 'incoming_message', 'message_object': ChatMessage})
        or None if the payload is irrelevant or cannot be processed.
    """
    logger.debug(f"Parsing webhook payload: {json.dumps(payload, indent=2)}")

    # Basic validation of payload structure
    if not payload or payload.get("object") != "whatsapp_business_account":
        logger.warning("Received non-WhatsApp or invalid webhook payload.")
        return None

    processed_info = None # Store info about the primary event processed

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "messages":
                value = change.get("value", {})
                metadata = value.get("metadata", {}) # Contains phone_number_id, display_phone_number
                contacts_data = value.get("contacts", []) # Info about the sender/recipient
                messages_data = value.get("messages", []) # Incoming message details
                statuses_data = value.get("statuses", []) # Status update details

                # --- Handle Incoming Messages ---
                if messages_data:
                    for msg_data in messages_data:
                        try:
                            sender_wa_id = msg_data.get("from")
                            message_id = msg_data.get("id") # WAMID of the incoming message
                            timestamp_ms_str = msg_data.get("timestamp") # WhatsApp timestamp (string)
                            msg_type = msg_data.get("type")

                            if not all([sender_wa_id, message_id, msg_type, timestamp_ms_str]):
                                logger.warning(f"Skipping incomplete incoming message data: {msg_data}")
                                continue

                            # Check if message already processed (webhooks can be resent)
                            if ChatMessage.objects.filter(message_id=message_id).exists():
                                logger.info(f"Incoming message {message_id} already processed. Skipping.")
                                continue

                            # Get sender's profile name from contacts_data if available
                            profile_name = next((c.get("profile", {}).get("name") for c in contacts_data if c.get("wa_id") == sender_wa_id), None)

                            # Get or create contact, update name if changed
                            contact, created = Contact.objects.update_or_create(
                                wa_id=sender_wa_id,
                                defaults={'name': profile_name} if profile_name else {} # Only update name if provided
                            )
                            if created:
                                logger.info(f"Created new contact via incoming message: {sender_wa_id} ({profile_name})")
                            elif profile_name and contact.name != profile_name:
                                contact.name = profile_name # Update name if changed
                                contact.save(update_fields=['name'])
                                logger.info(f"Updated contact name for {sender_wa_id} to '{profile_name}'")

                            # ***** Integration Point: Link contact to nursery customer/user if needed *****
                            # if created or not contact_is_linked(contact):
                            #     find_and_link_nursery_customer(contact) # Implement this logic

                            # Extract message content based on type
                            text_content = None
                            media_url = None
                            # TODO: Implement media download logic if needed.
                            # Requires separate API call using media ID. Store temporary placeholder for now.
                            if msg_type == 'text':
                                text_content = msg_data.get("text", {}).get("body")
                            elif msg_type == 'reaction':
                                reaction_emoji = msg_data.get('reaction', {}).get('emoji', '?')
                                reacted_msg_id = msg_data.get('reaction', {}).get('message_id')
                                text_content = f"Reacted '{reaction_emoji}' to message {reacted_msg_id}"
                            elif msg_type in ['image', 'video', 'audio', 'document', 'sticker']:
                                media_info = msg_data.get(msg_type, {})
                                media_id = media_info.get('id')
                                caption = media_info.get('caption') # Caption might exist
                                filename = media_info.get('filename') # For documents
                                # Placeholder text, actual media requires download via API
                                text_content = f"Received {msg_type}"
                                if caption: text_content += f" with caption: {caption}"
                                if filename: text_content += f" (Filename: {filename})"
                                logger.info(f"Received {msg_type} with media ID {media_id} from {sender_wa_id}. Manual download required.")
                                # media_url = download_whatsapp_media(media_id) # Implement this if needed
                            elif msg_type == 'location':
                                loc = msg_data.get('location', {})
                                text_content = f"Shared location: Lat {loc.get('latitude')}, Lon {loc.get('longitude')}"
                                if loc.get('name'): text_content += f" ({loc.get('name')})"
                            elif msg_type == 'contacts':
                                contacts_shared = msg_data.get('contacts', [])
                                names = [c.get('name', {}).get('formatted_name', 'Unknown') for c in contacts_shared]
                                text_content = f"Shared contact(s): {', '.join(names)}"
                            elif msg_type == 'interactive':
                                # Handle button replies or list replies
                                interactive_data = msg_data.get('interactive', {})
                                interactive_type = interactive_data.get('type')
                                if interactive_type == 'button_reply':
                                     reply_info = interactive_data.get('button_reply', {})
                                     text_content = f"Button reply: '{reply_info.get('title')}' (ID: {reply_info.get('id')})"
                                elif interactive_type == 'list_reply':
                                     reply_info = interactive_data.get('list_reply', {})
                                     text_content = f"List reply: '{reply_info.get('title')}' (ID: {reply_info.get('id')})"
                                else:
                                     text_content = f"Received interactive message type: {interactive_type}"
                            elif msg_type == 'unsupported':
                                 text_content = "Received an unsupported message type (e.g., poll)."
                            else:
                                text_content = f"Received unhandled message type: {msg_type}"
                                logger.warning(f"Received unhandled message type '{msg_type}' from {sender_wa_id}. Payload: {msg_data}")

                            # Convert WhatsApp timestamp (seconds string) to datetime
                            whatsapp_dt = None
                            try:
                                whatsapp_dt = datetime.fromtimestamp(int(timestamp_ms_str), tz=timezone.utc)
                            except (ValueError, TypeError):
                                logger.warning(f"Could not parse WhatsApp timestamp: {timestamp_ms_str}")

                            # ***** Integration Point: Find related nursery object based on message content *****
                            # related_order = find_related_order_from_text(text_content) # Implement this

                            # Create ChatMessage object in DB
                            message = ChatMessage.objects.create(
                                message_id=message_id,
                                contact=contact,
                                direction='IN',
                                status='RECEIVED', # Incoming messages are just received
                                message_type=msg_type,
                                text_content=text_content,
                                media_url=media_url, # Store placeholder or actual URL if downloaded
                                timestamp=timezone.now(), # When we processed it
                                whatsapp_timestamp=whatsapp_dt,
                                # related_order=related_order,
                            )
                            logger.info(f"Processed incoming {msg_type} message {message_id} from {sender_wa_id}")
                            # Store primary processed event info
                            if not processed_info:
                                processed_info = {'type': 'incoming_message', 'message_object': message}

                        except Exception as msg_proc_err:
                             logger.exception(f"Error processing one incoming message: {msg_proc_err}. Data: {msg_data}")
                             # Continue processing other messages in the batch if possible

                # --- Handle Message Status Updates ---
                elif statuses_data:
                    for status_data in statuses_data:
                        try:
                            message_wamid = status_data.get("id") # WAMID of the original *outgoing* message
                            status = status_data.get("status") # sent, delivered, read, failed
                            timestamp_ms_str = status_data.get("timestamp")
                            recipient_id = status_data.get("recipient_id") # Should match the contact WA ID
                            conversation_id = status_data.get("conversation", {}).get("id") # Optional conversation context
                            pricing_model = status_data.get("pricing", {}).get("pricing_model") # Optional pricing context
                            errors = status_data.get("errors") # Present if status is 'failed'

                            if not message_wamid or not status:
                                logger.warning(f"Skipping incomplete status update data: {status_data}")
                                continue

                            # Find the original outgoing message in our database using the WAMID
                            try:
                                message = ChatMessage.objects.get(message_id=message_wamid, direction='OUT')
                            except ChatMessage.DoesNotExist:
                                logger.warning(f"Received status update for unknown outgoing message WAMID: {message_wamid}")
                                continue # Cannot update status if we don't have the original message

                            # Map WhatsApp status to our model choices
                            new_status_map = {
                                'sent': 'SENT', # Confirms API acceptance, usually already set by us
                                'delivered': 'DELIVERED',
                                'read': 'READ',
                                'failed': 'FAILED',
                            }
                            new_status = new_status_map.get(status.lower())

                            if new_status:
                                # Update status only if it's progressing or failed
                                # Define status progression order
                                current_status_order = ['PENDING', 'SENT', 'DELIVERED', 'READ']
                                try:
                                    # Allow update if new status is FAILED or comes after current status
                                    current_index = current_status_order.index(message.status)
                                    new_index = current_status_order.index(new_status)
                                    should_update = (new_index >= current_index) or (new_status == 'FAILED')
                                except ValueError:
                                     # If current status isn't in the list (e.g., FAILED), allow update
                                     should_update = True

                                if should_update:
                                    message.status = new_status
                                    update_fields = ['status']
                                    if new_status == 'FAILED' and errors:
                                        # Log the error details from WhatsApp
                                        message.error_message = json.dumps(errors)
                                        update_fields.append('error_message')
                                    # Optionally update timestamp? Maybe add a separate 'last_status_update_time'?
                                    message.save(update_fields=update_fields)
                                    logger.info(f"Updated status for outgoing message {message_wamid} to {new_status}")
                                    if not processed_info: # Store primary event info
                                        processed_info = {'type': 'status_update', 'message_id': message_wamid, 'status': new_status}

                                    # ***** Integration Point: Update Marketing CampaignContact status *****
                                    try:
                                         # Import locally to avoid potential circular dependency at module level
                                         from .models import CampaignContact
                                         updated_count = CampaignContact.objects.filter(message_id=message_wamid).update(status=new_status)
                                         if updated_count > 0:
                                             logger.info(f"Updated status for CampaignContact linked to message {message_wamid} to {new_status}")
                                    except ImportError: pass # Ignore if marketing models aren't used
                                    except Exception as cc_update_err:
                                         logger.error(f"Error updating CampaignContact status for message {message_wamid}: {cc_update_err}")

                                else:
                                     logger.info(f"Ignoring status update for {message_wamid}: '{status}' ({new_status}) is not newer than current status '{message.status}'")
                            else:
                                 logger.warning(f"Received unknown status type '{status}' for message {message_wamid}")

                        except Exception as status_proc_err:
                            logger.exception(f"Error processing one status update: {status_proc_err}. Data: {status_data}")
                            # Continue processing other statuses in the batch if possible
            else:
                # Log if the change field is something other than 'messages'
                other_field = change.get("field")
                if other_field:
                    logger.debug(f"Ignoring non-messages change field in webhook: {other_field}")

    return processed_info # Return info about the first significant event processed


# --- Fetching Templates ---
def fetch_whatsapp_templates_from_api(settings: WhatsAppSettings) -> list | None:
    """
    Fetches approved message templates from the WhatsApp Cloud API.

    Args:
        settings: The active WhatsAppSettings object.

    Returns:
        A list of template dictionaries for APPROVED templates from the API response,
        or None if an error occurs during the fetch.
    """
    if not settings.whatsapp_business_account_id:
        logger.error("Cannot fetch templates: WhatsApp Business Account ID is not configured.")
        raise ValueError("WhatsApp Business Account ID not configured.") # Raise error to signal config issue

    api_url = f"{GRAPH_API_URL}/{settings.whatsapp_business_account_id}/message_templates"
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    # Request specific fields needed for display and sending
    # Include 'quality_score' if you want to monitor template quality
    params = {
        "fields": "name,status,category,language,components,quality_score",
        "limit": 100 # Fetch up to 100 templates per request (adjust if needed)
    }
    all_templates = []
    page_count = 0

    try:
        logger.info(f"Fetching message templates for WABA ID: {settings.whatsapp_business_account_id}")
        while api_url: # Loop to handle pagination
             page_count += 1
             logger.debug(f"Fetching template page {page_count} from {api_url}")
             # Params only needed for first page request
             current_params = params if page_count == 1 else None
             response = requests.get(api_url, headers=headers, params=current_params, timeout=30)
             response.raise_for_status() # Check for HTTP errors
             data = response.json()

             current_page_templates = data.get("data", [])
             all_templates.extend(current_page_templates)

             # Check for next page URL in pagination cursor
             api_url = data.get("paging", {}).get("next")
             if api_url:
                 logger.debug("Found next page for templates...")
             else:
                  logger.debug("No more template pages found.")

        # Filter for templates that are currently approved
        approved_templates = [t for t in all_templates if t.get('status') == 'APPROVED']
        logger.info(f"Fetched {len(all_templates)} total templates, {len(approved_templates)} are APPROVED.")
        return approved_templates

    except requests.exceptions.RequestException as e:
        error_message = f"HTTP Error fetching templates: {e}. Response: {e.response.text if e.response else 'N/A'}"
        logger.error(error_message)
        return None # Indicate failure
    except Exception as e:
        logger.exception(f"Unexpected error fetching templates: {e}") # Log full traceback
        return None


# --- Optional: Webhook Signature Verification ---
def verify_whatsapp_signature(payload: bytes, signature: str | None, secret: str | None) -> bool:
    """
    Verifies the X-Hub-Signature-256 header from WhatsApp webhooks.

    Args:
        payload: The raw request body (bytes).
        signature: The value of the X-Hub-Signature-256 header (e.g., 'sha256=...').
        secret: Your WhatsApp App Secret (from Meta Developer Portal).

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not signature or not secret:
        logger.warning("Cannot verify webhook signature: Missing signature header or App Secret.")
        # Fail safe: assume invalid if cannot verify
        return False

    try:
        # Extract the hash from the signature header (format: sha256=hash)
        if not signature.startswith('sha256='):
             logger.warning(f"Invalid signature format received: {signature}")
             return False
        expected_hash = signature[len('sha256='):]

        # Calculate the expected hash using HMAC-SHA256
        byte_secret = secret.encode('utf-8')
        calculated_hash_obj = hmac.new(byte_secret, payload, hashlib.sha256)
        calculated_hash = calculated_hash_obj.hexdigest()

        # Compare hashes securely to prevent timing attacks
        is_valid = hmac.compare_digest(expected_hash, calculated_hash)
        if not is_valid:
             logger.warning(f"Webhook signature mismatch. Header: {expected_hash}, Calculated: {calculated_hash}")
        else:
             logger.debug("Webhook signature verified successfully.")
        return is_valid
    except Exception as e:
        logger.error(f"Error during webhook signature verification: {e}")
        return False


# --- Optional: Media Upload/Download ---
# Implement functions to upload media (to get a media ID for sending)
# and download media (using a media ID from an incoming message) if needed.
# These involve separate Graph API endpoints like POST /{Phone-Number-ID}/media
# and GET /{Media-ID}, and require handling file streams and authentication.

# Example placeholder:
# def download_whatsapp_media(media_id):
#     """Downloads media file associated with the given media ID."""
#     # 1. Get Media URL: Call GET /{media_id} with token to get a temporary URL
#     # 2. Download File: Make a GET request to the temporary URL (without token)
#     # 3. Save/Process File: Save the response content to a file or process in memory
#     logger.info(f"Placeholder: Download media for ID {media_id}")
#     return None # Return file path or content
