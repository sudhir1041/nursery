from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db import transaction
from django.utils import timezone
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import json
import logging

# Import necessary models and utils from your app
from .models import Contact, ChatMessage, BotResponse, AutoReply, MarketingCampaign, CampaignContact
# Assume utils handle the actual API calls and DB saving correctly
from .utils import parse_incoming_whatsapp_message, send_whatsapp_message, download_whatsapp_media # Import download util
# Import the helper function from views (ensure no circular imports)
# It might be better to move handle_bot_or_autoreply to utils.py
try:
    from .views import handle_bot_or_autoreply
except ImportError:
    # Define a dummy if there's a circular import - move the function later
    def handle_bot_or_autoreply(message_obj):
        logger.warning("handle_bot_or_autoreply could not be imported, likely circular import.")
        pass


logger = logging.getLogger(__name__)

# --- Task for Processing Incoming Webhooks ---

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_whatsapp_webhook_task(self, payload_str):
    """
    Celery task to process incoming webhook payload asynchronously.
    Parses the payload, saves messages/updates status, broadcasts to channels,
    and triggers bot/auto-reply logic.
    """
    logger.info(f"Celery task [ID: {self.request.id}]: Starting webhook payload processing.")
    try:
        payload = json.loads(payload_str)
        # Assume parse_incoming_whatsapp_message correctly saves ChatMessage
        # and returns dict including {'type': '...', 'message_object': ChatMessage} or {'type': '...', 'status_data': {...}}
        processed_data = parse_incoming_whatsapp_message(payload)

        data_type = processed_data.get('type') if processed_data else None

        if data_type == 'incoming_message':
            message_obj = processed_data.get('message_object')
            if message_obj and isinstance(message_obj, ChatMessage):
                room_group_name = f'chat_{message_obj.contact.wa_id}'
                
                # Handle media messages
                msg_type = message_obj.message_type
                if msg_type in ['image', 'video', 'audio', 'document']:
                    msg_data = payload.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
                    media_info = msg_data.get(msg_type, {})
                    media_id_from_payload = media_info.get('id')
                    caption = media_info.get('caption')
                    filename = media_info.get('filename')
                    text_content = caption or f"Received {msg_type}"
                    if filename:
                        text_content += f" (Filename: {filename})"
                    logger.info(f"Received {msg_type} media ID {media_id_from_payload} from {message_obj.contact.wa_id}.")

                    # Attempt to download media
                    downloaded_media = None
                    if media_id_from_payload:
                        media_result = download_whatsapp_media(media_id_from_payload)
                        if media_result:
                            media_content_bytes, content_type = media_result
                            # Save to Django Media Storage
                            from django.core.files.base import ContentFile
                            file_name_to_save = f"whatsapp_media/{message_obj.message_id}_{filename or media_id_from_payload}"
                            saved_path = default_storage.save(file_name_to_save, ContentFile(media_content_bytes))
                            media_url = default_storage.url(saved_path)
                            logger.info(f"Saved downloaded media to: {saved_path}")
                            
                            # Update message object with media info
                            message_obj.media_url = media_url
                            message_obj.media_id = media_id_from_payload
                            message_obj.text_content = text_content
                            message_obj.save()

                # Prepare data including message_type and media_url
                message_data = {
                    'message_id': message_obj.message_id,
                    'text_content': message_obj.text_content, # Caption for media
                    'timestamp': message_obj.timestamp.isoformat(),
                    'direction': 'IN',
                    'status': message_obj.status, # Should be 'RECEIVED'
                    'message_type': message_obj.message_type, # e.g., 'text', 'image', 'document'
                    'template_name': message_obj.template_name,
                    'media_url': message_obj.media_url, # URL if available (might be temporary)
                    'filename': filename if 'filename' in locals() else None
                }
                # --- Send to Channel Layer ---
                try:
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        room_group_name,
                        {'type': 'chat_message', 'message': message_data}
                    )
                    logger.info(f"Celery task [ID: {self.request.id}]: Sent incoming message {message_obj.message_id} (type: {message_obj.message_type}) to channel group {room_group_name}")
                except Exception as e:
                    logger.exception(f"Celery task [ID: {self.request.id}]: Failed to send message to channel layer for {message_obj.contact.wa_id}: {e}")

                # --- Handle Bot/Auto-Reply (only for text messages usually) ---
                if message_obj.message_type == 'text':
                    handle_bot_or_autoreply(message_obj)
            else:
                logger.warning(f"Celery task [ID: {self.request.id}]: parse_incoming_whatsapp_message indicated incoming message but did not return a valid message_object.")

        elif data_type == 'status_update':
             status_data = processed_data.get('status_data')
             if status_data:
                 try:
                     channel_layer = get_channel_layer()
                     wa_id = status_data.get('wa_id')
                     if wa_id:
                         room_group_name = f'chat_{wa_id}'
                         async_to_sync(channel_layer.group_send)(
                             room_group_name,
                             {'type': 'status_update', 'data': status_data}
                         )
                         logger.info(f"Celery task [ID: {self.request.id}]: Broadcasted status update for message {status_data.get('message_id')} to {room_group_name}")
                     else:
                          logger.warning(f"Celery task [ID: {self.request.id}]: Cannot broadcast status update, wa_id not found in processed data: {status_data}")
                 except Exception as e:
                    logger.exception(f"Celery task [ID: {self.request.id}]: Failed to send status update to channel layer: {e}")
        elif processed_data:
             logger.info(f"Celery task [ID: {self.request.id}]: Processed webhook event type: {data_type}")
        else:
             logger.warning(f"Celery task [ID: {self.request.id}]: parse_incoming_whatsapp_message returned None or empty data.")

        logger.info(f"Celery task [ID: {self.request.id}]: Webhook payload processing finished successfully.")

    except json.JSONDecodeError:
        logger.error(f"Celery task [ID: {self.request.id}]: Invalid JSON in payload: {payload_str[:500]}...")
    except Exception as exc:
        logger.exception(f"Celery task [ID: {self.request.id}]: Error processing webhook payload.")
        raise self.retry(exc=exc)


# --- Task for Sending a Single Message (Updated for Media) ---

@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_whatsapp_message_task(self, recipient_wa_id, message_type, text_content=None, template_name=None, components=None, media_id=None, media_link=None, filename=None, campaign_contact_id=None):
    """
    Celery task to send an outgoing WhatsApp message via the API utility.
    Handles different message types including media.
    """
    logger.info(f"Celery task [ID: {self.request.id}]: Attempting to send {message_type} message to {recipient_wa_id}")
    message_obj = None
    final_status = 'FAILED'
    error_detail = None

    try:
        # Call the utility function which handles API call AND saving ChatMessage
        # Assume it now accepts media_id/media_link/filename
        message_obj = send_whatsapp_message(
            recipient_wa_id=recipient_wa_id,
            message_type=message_type,
            text_content=text_content, # Caption for media, body for text/template
            template_name=template_name,
            components=components,
            media_id=media_id, # Pass media ID obtained from WhatsApp upload API
            media_link=media_link, # Or pass a public link for WhatsApp to fetch
            filename=filename # Optional filename for documents
        )

        if message_obj:
            final_status = message_obj.status
            logger.info(f"Celery task [ID: {self.request.id}]: Message {message_obj.message_id} ({final_status}) sent/queued successfully to {recipient_wa_id}.")

            # --- Broadcast the SENT/PENDING message back via WebSocket ---
            try:
                channel_layer = get_channel_layer()
                room_group_name = f'chat_{recipient_wa_id}'
                message_data = {
                    'message_id': message_obj.message_id,
                    'text_content': message_obj.text_content,
                    'timestamp': message_obj.timestamp.isoformat(),
                    'direction': 'OUT',
                    'status': message_obj.status,
                    'message_type': message_obj.message_type,
                    'template_name': message_obj.template_name,
                    'media_url': message_obj.media_url, # May be null initially
                    # 'filename': message_obj.filename # Include if available
                }
                async_to_sync(channel_layer.group_send)(
                    room_group_name,
                    {'type': 'chat_message', 'message': message_data}
                )
                logger.info(f"Celery task [ID: {self.request.id}]: Broadcasted sent message {message_obj.message_id} to channel group {room_group_name}")
            except Exception as e:
                 logger.exception(f"Celery task [ID: {self.request.id}]: Failed to broadcast sent message status for {recipient_wa_id}: {e}")
        else:
            logger.error(f"Celery task [ID: {self.request.id}]: send_whatsapp_message utility failed for {recipient_wa_id}.")
            error_detail = "Failed in send_whatsapp_message utility (check util logs)."

    except Exception as exc:
        logger.exception(f"Celery task [ID: {self.request.id}]: Unexpected error sending message to {recipient_wa_id}.")
        error_detail = str(exc)
        try:
            raise self.retry(exc=exc)
        except Exception as retry_exc:
             logger.error(f"Celery task [ID: {self.request.id}]: Max retries reached or retry failed for sending to {recipient_wa_id}. Marking as FAILED.")
             final_status = 'FAILED'

    # --- Update CampaignContact status if applicable ---
    if campaign_contact_id:
        try:
            CampaignContact.objects.filter(pk=campaign_contact_id).update(
                status=final_status,
                message_id=message_obj.message_id if message_obj else None,
                sent_time=message_obj.timestamp if message_obj and final_status != 'FAILED' else None,
                error_message=error_detail if final_status == 'FAILED' else None
            )
            logger.info(f"Celery task [ID: {self.request.id}]: Updated CampaignContact {campaign_contact_id} status to {final_status}.")
        except Exception as e:
             logger.exception(f"Celery task [ID: {self.request.id}]: Failed to update CampaignContact status for ID {campaign_contact_id}: {e}")

    return message_obj.message_id if message_obj else None


# --- Task for Sending Bulk Campaign Messages ---

@shared_task(bind=True)
def send_bulk_campaign_messages_task(self, campaign_id):
    """
    Celery task to iterate through campaign recipients and queue individual message sending tasks.
    """
    logger.info(f"Celery task [ID: {self.request.id}]: Starting bulk send for campaign ID: {campaign_id}")
    try:
        campaign = MarketingCampaign.objects.select_related('template').get(pk=campaign_id)
        if campaign.status != 'SENDING':
            logger.warning(f"Celery task [ID: {self.request.id}]: Campaign {campaign_id} status is '{campaign.status}', not 'SENDING'. Aborting.")
            return f"Campaign {campaign_id} not in SENDING state."

        pending_recipients = CampaignContact.objects.filter(campaign=campaign, status='PENDING').select_related('contact')
        recipient_count = pending_recipients.count()
        logger.info(f"Celery task [ID: {self.request.id}]: Found {recipient_count} pending recipients for campaign {campaign_id}.")

        if recipient_count == 0:
             # ... (handle completion as before) ...
             logger.info(f"Celery task [ID: {self.request.id}]: No pending recipients found for campaign {campaign_id}. Marking as completed.")
             campaign.status = 'COMPLETED'; campaign.completed_at = timezone.now()
             campaign.save(update_fields=['status', 'completed_at'])
             return f"Campaign {campaign_id} completed (no pending recipients)."

        queued_count = 0
        for recipient in pending_recipients.iterator():
            try:
                # --- Prepare Components (CRITICAL: Implement this logic) ---
                # This needs to correctly format the components JSON based on the template
                # and the recipient's specific variables stored in recipient.template_variables
                # Example placeholder - replace with your actual formatting logic:
                formatted_components = campaign.template.components # Replace with actual formatting
                # formatted_components = format_template_components(campaign.template.components, recipient.template_variables)

                # Queue the individual message sending task
                send_whatsapp_message_task.delay(
                    recipient_wa_id=recipient.contact.wa_id,
                    message_type='template',
                    template_name=campaign.template.name,
                    components=formatted_components, # Pass the correctly formatted components
                    campaign_contact_id=recipient.id
                )
                queued_count += 1
            except Exception as e:
                 logger.error(f"Celery task [ID: {self.request.id}]: Failed to queue message for recipient {recipient.contact.wa_id} (CC ID: {recipient.id}) in campaign {campaign_id}: {e}")
                 recipient.status = 'FAILED'; recipient.error_message = f"Failed to queue send task: {e}"
                 recipient.save(update_fields=['status', 'error_message'])

        logger.info(f"Celery task [ID: {self.request.id}]: Queued {queued_count} individual send tasks for campaign {campaign_id}.")
        # Mark campaign as completed after queueing (actual delivery tracked via webhooks)
        campaign.status = 'COMPLETED'; campaign.completed_at = timezone.now()
        campaign.save(update_fields=['status', 'completed_at'])
        logger.info(f"Celery task [ID: {self.request.id}]: Marked campaign {campaign_id} as COMPLETED after queueing tasks.")
        return f"Campaign {campaign_id}: Queued {queued_count} messages for sending."

    except MarketingCampaign.DoesNotExist:
        logger.error(f"Celery task [ID: {self.request.id}]: MarketingCampaign with ID {campaign_id} not found.")
        return f"Campaign ID {campaign_id} not found."
    except Exception as exc:
        logger.exception(f"Celery task [ID: {self.request.id}]: Unexpected error during bulk send for campaign {campaign_id}.")
        try: MarketingCampaign.objects.filter(pk=campaign_id).update(status='FAILED')
        except Exception as update_e: logger.error(f"Celery task [ID: {self.request.id}]: Also failed to update campaign {campaign_id} status to FAILED: {update_e}")
        raise self.retry(exc=exc)

