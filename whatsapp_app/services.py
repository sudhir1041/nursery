import requests
import json
import logging
import os  # Needed for upload_media

from django.conf import settings
from .models import WhatsappCredentials

# Get a logger instance for this module
logger = logging.getLogger(__name__)

# --- Configuration ---


def get_whatsapp_credentials():
    try:
        return WhatsappCredentials.objects.get(is_live_mode=True)
    except WhatsappCredentials.DoesNotExist:
        logger.error("No live WhatsApp credentials found.")
        return None




# Standard headers for JSON API calls
JSON_HEADERS = {
    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}


def send_whatsapp_message(sender_number, recipient_number, message_body):
    """
    Sends a WhatsApp message using the provided sender number, recipient number, and message body.

    Args:
        sender_number: The WhatsApp number from which the message will be sent.
        recipient_number: The WhatsApp number to which the message will be sent.
        message_body: The text content of the message.

    Returns:
        A dictionary containing the API response on success, or None on failure.
    """
    credentials = get_whatsapp_credentials()
    if not credentials:
        return None

    API_VERSION = "v19.0"
    BASE_API_URL = f"https://graph.facebook.com/{API_VERSION}"
    PHONE_NUMBER_BASE_URL = f"{BASE_API_URL}/{credentials.phone_number_id}"

    if sender_number != credentials.phone_number:
        logger.error(
            f"Sender number {sender_number} does not match live credentials {credentials.phone_number}."
        )
        return None

    response = send_text_message(
        recipient_wa_id=recipient_number, message_body=message_body,PHONE_NUMBER_BASE_URL=PHONE_NUMBER_BASE_URL
    )
    return response


# --- Service Functions ---

def send_text_message(recipient_wa_id: str, message_body: str) -> dict | None:
    """
    Sends a plain text message to a WhatsApp user.

    Args:
        recipient_wa_id: The WhatsApp ID (phone number) of the recipient.
        message_body: The text content of the message.

    Returns:
        A dictionary containing the API response (usually includes message ID)
        on success, or None on failure.
    """
    credentials = get_whatsapp_credentials()
    if not credentials:
        return None

    API_VERSION = "v19.0"
    BASE_API_URL = f"https://graph.facebook.com/{API_VERSION}"
    PHONE_NUMBER_BASE_URL = f"{BASE_API_URL}/{credentials.phone_number_id}"
    url = f"{PHONE_NUMBER_BASE_URL}/messages"  
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_wa_id,
        "type": "text",
        "text": {
            "preview_url": False,  # Set to True to enable link previews if needed
            "body": message_body
        }
    }
    payload_json = json.dumps(payload)

    logger.info(f"Attempting to send text message to {recipient_wa_id}...")
    logger.debug(f"Request URL: {url}")
    logger.debug(f"Request Payload: {payload_json}") # Be careful logging full PII in production

    try:
        response = requests.post(url, headers=JSON_HEADERS, data=payload_json, timeout=15) # Timeout in seconds
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX, 5XX)

        response_data = response.json()
        logger.info(f"Successfully sent message to {recipient_wa_id}. Response: {response_data}")
        # Expected response format on success: {'messaging_product': 'whatsapp', 'contacts': [{'input': '...', 'wa_id': '...'}], 'messages': [{'id': 'wamid.XXXX...'}]}
        return response_data

    except requests.exceptions.Timeout:
        logger.error(f"Request timed out while sending message to {recipient_wa_id}.")
        return None
    except requests.exceptions.RequestException as e:
        error_content = e.response.content.decode('utf-8') if e.response and e.response.content else "No Response Content"
        status_code = e.response.status_code if e.response is not None else "N/A"
        logger.error(
            f"HTTP Error sending message to {recipient_wa_id}: "
            f"Status={status_code}, Error={e}, Response={error_content}"
        )
        # You might want to parse the error_content JSON here for specific WhatsApp error codes
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred sending message to {recipient_wa_id}: {e}")
        return None


def upload_media(file_path: str, mime_type: str) -> str | None:
    """
    Uploads a media file to WhatsApp servers to get a reusable media ID.

    Args:
        file_path: The local path to the media file.
        mime_type: The MIME type of the file (e.g., 'image/jpeg', 'application/pdf').

    Returns:
        The WhatsApp media ID string on success, or None on failure.
    """
    url = f"{PHONE_NUMBER_BASE_URL}/media"
    
    credentials = get_whatsapp_credentials()
    if not credentials:
        return None
    
    API_VERSION = "v19.0"
    BASE_API_URL = f"https://graph.facebook.com/{API_VERSION}"
    PHONE_NUMBER_BASE_URL = f"{BASE_API_URL}/{credentials.phone_number_id}"    data = {
        'messaging_product': 'whatsapp'
    }
    # Headers for multipart/form-data - only Authorization is strictly needed,
    # requests handles the Content-Type for multipart.
    upload_headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
    }

    logger.info(f"Attempting to upload media file: {file_path} ({mime_type})")
    logger.debug(f"Request URL: {url}")

    try:
        with open(file_path, 'rb') as f:
            files = {
                'file': (os.path.basename(file_path), f, mime_type)
            }
            response = requests.post(url, headers=upload_headers, data=data, files=files, timeout=30) # Longer timeout for uploads
            response.raise_for_status()

            response_data = response.json()
            media_id = response_data.get('id')

            if not media_id:
                logger.error(f"Media ID missing in successful upload response for {file_path}. Response: {response_data}")
                return None

            logger.info(f"Successfully uploaded media {file_path}. Media ID: {media_id}")
            # Expected response format on success: {'id': 'MEDIA_ID_STRING'}
            return media_id

    except FileNotFoundError:
        logger.error(f"Media file not found at path: {file_path}")
        return None
    except requests.exceptions.Timeout:
        logger.error(f"Request timed out while uploading media file {file_path}.")
        return None
    except requests.exceptions.RequestException as e:
        error_content = e.response.content.decode('utf-8') if e.response and e.response.content else "No Response Content"
        status_code = e.response.status_code if e.response is not None else "N/A"
        logger.error(
            f"HTTP Error uploading media file {file_path}: "
            f"Status={status_code}, Error={e}, Response={error_content}"
        )
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred uploading media file {file_path}: {e}")
        return None


ALLOWED_MEDIA_TYPES = ['image', 'video', 'audio', 'document', 'sticker']

def send_media_message(recipient_wa_id: str, media_type: str, media_id_or_url: str, is_url: bool = False, caption: str | None = None, filename: str | None = None) -> dict | None:
    """
    Sends a media message (image, video, audio, document, sticker) using a media ID or URL.

    Args:
        recipient_wa_id: The WhatsApp ID of the recipient.
        media_type: Type of media ('image', 'video', 'audio', 'document', 'sticker').
        media_id_or_url: WhatsApp Media ID (from upload_media) or a public HTTPS URL.
        is_url: Set to True if media_id_or_url is a URL, False if it's a Media ID.
        caption: Optional caption for image, video, document.
        filename: Optional filename, primarily recommended for documents sent via URL.

    Returns:
        A dictionary containing the API response on success, or None on failure.
    """
    if media_type not in ALLOWED_MEDIA_TYPES:
        logger.error(f"Invalid media_type '{media_type}' provided. Must be one of {ALLOWED_MEDIA_TYPES}")
        return None

    credentials = get_whatsapp_credentials()
    if not credentials:
        return None
    API_VERSION = "v19.0"
    BASE_API_URL = f"https://graph.facebook.com/{API_VERSION}"
    PHONE_NUMBER_BASE_URL = f"{BASE_API_URL}/{credentials.phone_number_id}"
    url = f"{PHONE_NUMBER_BASE_URL}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_wa_id,
        "type": media_type,
        media_type: {} # Initialize the inner media object
    }

    # Set ID or Link based on the flag
    if is_url:
        payload[media_type]['link'] = media_id_or_url
    else:
        payload[media_type]['id'] = media_id_or_url

    # Add caption if provided and applicable
    if caption and media_type in ['image', 'video', 'document']:
        payload[media_type]['caption'] = caption

    # Add filename if provided and applicable (mainly for documents)
    if filename and media_type == 'document':
         payload[media_type]['filename'] = filename

    payload_json = json.dumps(payload)

    logger.info(f"Attempting to send {media_type} message to {recipient_wa_id}...")
    logger.debug(f"Request URL: {url}")
    logger.debug(f"Request Payload: {payload_json}")

    try:
        response = requests.post(url, headers=JSON_HEADERS, data=payload_json, timeout=15)
        response.raise_for_status()

        response_data = response.json()
        logger.info(f"Successfully sent {media_type} message to {recipient_wa_id}. Response: {response_data}")
        return response_data

    except requests.exceptions.Timeout:
        logger.error(f"Request timed out while sending {media_type} message to {recipient_wa_id}.")
        return None
    except requests.exceptions.RequestException as e:
        error_content = e.response.content.decode('utf-8') if e.response and e.response.content else "No Response Content"
        status_code = e.response.status_code if e.response is not None else "N/A"
        logger.error(
            f"HTTP Error sending {media_type} message to {recipient_wa_id}: "
            f"Status={status_code}, Error={e}, Response={error_content}"
        )
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred sending {media_type} message to {recipient_wa_id}: {e}")
        return None


def send_template_message(recipient_wa_id: str, template_name: str, language_code: str = 'en_US', components: list | None = None) -> dict | None:
    """
    Sends a message based on a pre-approved WhatsApp template.

    Args:
        recipient_wa_id: The WhatsApp ID of the recipient.
        template_name: The exact name of the approved template.
        language_code: The language code (e.g., 'en_US', 'en', 'hi'). Defaults to 'en_US'.
        components: (Optional) A list of component objects for header/body variables
                    and button payloads. Structure must match WhatsApp API requirements.
                    See: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages#template-messages
                    Example:
                    [
                        {"type": "header", "parameters": [{"type": "image", "image": {"id": "MEDIA_ID"}}]},
                        {"type": "body", "parameters": [{"type": "text", "text": "Value1"}, {"type": "text", "text": "Value2"}]},
                        {"type": "button", "sub_type": "quick_reply", "index": "0", "parameters": [{"type": "payload", "payload": "Payload0"}]}
                    ]

    Returns:
        A dictionary containing the API response on success, or None on failure.
    """
    url = f"{PHONE_NUMBER_BASE_URL}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_wa_id,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": language_code
            }
        }
    }

    # Add components only if provided
    if components:
        payload["template"]["components"] = components

    payload_json = json.dumps(payload)

    logger.info(f"Attempting to send template '{template_name}' ({language_code}) message to {recipient_wa_id}...")
    logger.debug(f"Request URL: {url}")
    logger.debug(f"Request Payload: {payload_json}")

    try:
        response = requests.post(url, headers=JSON_HEADERS, data=payload_json, timeout=15)
        response.raise_for_status()

        response_data = response.json()
        logger.info(f"Successfully sent template '{template_name}' message to {recipient_wa_id}. Response: {response_data}")
        return response_data

    except requests.exceptions.Timeout:
        logger.error(f"Request timed out while sending template '{template_name}' to {recipient_wa_id}.")
        return None
    except requests.exceptions.RequestException as e:
        error_content = e.response.content.decode('utf-8') if e.response and e.response.content else "No Response Content"
        status_code = e.response.status_code if e.response is not None else "N/A"
        logger.error(
            f"HTTP Error sending template '{template_name}' to {recipient_wa_id}: "
            f"Status={status_code}, Error={e}, Response={error_content}"
        )
        # Consider parsing error_content for specific template-related errors from WhatsApp
        # e.g., template not approved, wrong number of parameters, etc.
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred sending template '{template_name}' to {recipient_wa_id}: {e}")
        return None








# --- You can continue adding more functions like: ---
# def mark_message_as_read(message_id): ...
# def trigger_flow(recipient_wa_id, flow_id, flow_cta, screen_id, flow_action_payload=None): ...
# def get_media_url(media_id): ... # To retrieve the temporary URL for received media