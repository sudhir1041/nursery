from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db import transaction
from django.utils import timezone
# --- Added for Media Saving ---
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
# -----------------------------
import json
import logging

# Import necessary models and utils from your app
from .models import Contact, ChatMessage, BotResponse, AutoReply, MarketingCampaign, CampaignContact
# Assume utils handle the actual API calls and DB saving correctly
# --- CORRECTED IMPORT PATH ---
from .utils import (
    parse_incoming_whatsapp_message, send_whatsapp_message,
    download_whatsapp_media, handle_bot_or_autoreply # Import helper from utils
)

logger = logging.getLogger(__name__)

# --- Task for Processing Incoming Webhooks ---

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_whatsapp_webhook_task(self, payload_str):
    """
    Celery task to process incoming webhook payload asynchronously.
    Parses the payload, saves messages/updates status, downloads media,
    broadcasts to channels, and triggers bot/auto-reply logic.
    """
    logger.info(f"Celery task [ID: {self.request.id}]: Starting webhook payload processing.")
    try:
        payload = json.loads(payload_str)
        # This utility function should save the initial ChatMessage record
        # and return structured data, including the message object and media_id if present.
        processed_data = parse_incoming_whatsapp_message(payload)

        data_type = processed_data.get('type') if processed_data else None
        message_obj = processed_data.get('message_object') if processed_data else None

        # --- Handle Media Download FIRST if applicable ---
        media_url_for_db = None # URL to save in ChatMessage.media_url
        # Check if message_obj exists, is a ChatMessage, and has the temporary attribute
        if message_obj and isinstance(message_obj, ChatMessage) and hasattr(message_obj, 'media_id_from_payload') and message_obj.media_id_from_payload:
            logger.info(f"Task {self.request.id}: Media detected (ID: {message_obj.media_id_from_payload}) for message {message_obj.message_id}. Attempting download.")
            try:
                media_result = download_whatsapp_media(message_obj.media_id_from_payload)
                if media_result:
                    media_content_bytes, content_type = media_result
                    # --- Save the downloaded media ---
                    # Modify filename generation as needed
                    filename_from_payload = getattr(message_obj, 'filename', None) # Get filename if stored on message obj by parser
                    file_name_to_save = f"whatsapp_media/{message_obj.message_id}_{filename_from_payload or message_obj.media_id_from_payload or 'media'}"
                    saved_path = default_storage.save(file_name_to_save, ContentFile(media_content_bytes))
                    media_url_for_db = default_storage.url(saved_path) # Get the public URL
                    logger.info(f"Task {self.request.id}: Saved downloaded media for msg {message_obj.message_id} to: {saved_path} (URL: {media_url_for_db})")

                    # --- Update the ChatMessage record with the actual media URL ---
                    message_obj.media_url = media_url_for_db
                    # Optionally save filename if you added that field to ChatMessage model
                    # message_obj.filename = filename_from_payload_or_content_type
                    message_obj.save(update_fields=['media_url']) # Add 'filename' if needed

                else:
                    logger.error(f"Task {self.request.id}: Failed to download media for ID {message_obj.media_id_from_payload}")
            except Exception as download_err:
                 logger.exception(f"Task {self.request.id}: Error during media download/saving for media ID {message_obj.media_id_from_payload}: {download_err}")


        # --- Process based on event type ---
        if data_type == 'incoming_message':
            if message_obj and isinstance(message_obj, ChatMessage):
                room_group_name = f'chat_{message_obj.contact.wa_id}'
                message_data = { # Prepare data for WebSocket clients
                    'message_id': message_obj.message_id,
                    'text_content': message_obj.text_content,
                    'timestamp': message_obj.timestamp.isoformat(),
                    'direction': 'IN',
                    'status': message_obj.status,
                    'message_type': message_obj.message_type,
                    'template_name': message_obj.template_name,
                    'media_url': message_obj.media_url, # Send the potentially updated URL
                    # 'filename': message_obj.filename
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

                # --- Handle Bot/Auto-Reply (using imported function from utils) ---
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


# --- Task for Sending a Single Message ---
@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_whatsapp_message_task(self, recipient_wa_id, message_type, text_content=None, template_name=None, components=None, media_id=None, media_link=None, filename=None, campaign_contact_id=None):
    """ Celery task to send an outgoing WhatsApp message via the API utility. """
    # --- (Code for send_whatsapp_message_task remains the same) ---
    task_id = self.request.id; logger.info(f"Celery task [ID: {task_id}]: Starting send_whatsapp_message_task for {recipient_wa_id}, type: {message_type}"); logger.debug(f"Task [ID: {task_id}] Received args: recipient={recipient_wa_id}, type={message_type}, text={text_content}, template={template_name}, media_id={media_id}, media_link={media_link}, filename={filename}, campaign_contact_id={campaign_contact_id}")
    message_obj = None; final_status = 'FAILED'; error_detail = None
    try:
        logger.info(f"Task [ID: {task_id}]: Calling send_whatsapp_message utility...")
        message_obj = send_whatsapp_message(recipient_wa_id=recipient_wa_id, message_type=message_type, text_content=text_content, template_name=template_name, components=components, media_id=media_id, media_link=media_link, filename=filename)
        if message_obj:
            final_status = message_obj.status; logger.info(f"Celery task [ID: {task_id}]: Message {message_obj.message_id} ({final_status}) successfully processed by send_whatsapp_message utility for {recipient_wa_id}.")
            try: # Broadcast SENT/PENDING status
                channel_layer = get_channel_layer(); room_group_name = f'chat_{recipient_wa_id}'
                message_data = {'message_id': message_obj.message_id, 'text_content': message_obj.text_content, 'timestamp': message_obj.timestamp.isoformat(), 'direction': 'OUT', 'status': message_obj.status, 'message_type': message_obj.message_type, 'template_name': message_obj.template_name, 'media_url': message_obj.media_url}
                async_to_sync(channel_layer.group_send)(room_group_name, {'type': 'chat_message', 'message': message_data})
                logger.info(f"Celery task [ID: {task_id}]: Broadcasted sent message {message_obj.message_id} to channel group {room_group_name}")
            except Exception as e: logger.exception(f"Celery task [ID: {task_id}]: Failed to broadcast sent message status for {recipient_wa_id}: {e}")
        else: logger.error(f"Celery task [ID: {task_id}]: send_whatsapp_message utility returned None for {recipient_wa_id}."); error_detail = "Failed in send_whatsapp_message utility"
    except Exception as exc:
        logger.exception(f"Celery task [ID: {task_id}]: Unexpected error sending message to {recipient_wa_id}."); error_detail = str(exc)
        try: logger.warning(f"Task [ID: {task_id}]: Retrying due to error: {exc}"); raise self.retry(exc=exc)
        except Exception as retry_exc: logger.error(f"Celery task [ID: {task_id}]: Max retries reached or retry failed for sending to {recipient_wa_id}. Marking as FAILED."); final_status = 'FAILED'
    if campaign_contact_id: # Update CampaignContact status
        try:
            if CampaignContact: updated_count = CampaignContact.objects.filter(pk=campaign_contact_id).update(status=final_status, message_id=message_obj.message_id if message_obj else None, sent_time=message_obj.timestamp if message_obj and final_status != 'FAILED' else None, error_message=error_detail if final_status == 'FAILED' else None);
            if updated_count > 0: logger.info(f"Celery task [ID: {task_id}]: Updated CampaignContact {campaign_contact_id} status to {final_status}.")
            else: logger.warning(f"Celery task [ID: {task_id}]: Could not find CampaignContact ID {campaign_contact_id} to update.")
            else: logger.error(f"Celery task [ID: {task_id}]: Cannot update CampaignContact status - Model not imported.")
        except Exception as e: logger.exception(f"Celery task [ID: {task_id}]: Failed to update CampaignContact status for ID {campaign_contact_id}: {e}")
    logger.info(f"Celery task [ID: {task_id}]: Finished send_whatsapp_message_task for {recipient_wa_id}. Final status: {final_status}")
    return message_obj.message_id if message_obj else None


# --- Task for Sending Bulk Campaign Messages ---
@shared_task(bind=True)
def send_bulk_campaign_messages_task(self, campaign_id):
    """ Celery task to iterate through campaign recipients and queue individual message sending tasks. """
    # --- (Code for send_bulk_campaign_messages_task remains the same) ---
    logger.info(f"Celery task [ID: {self.request.id}]: Starting bulk send for campaign ID: {campaign_id}")
    try:
        campaign = MarketingCampaign.objects.select_related('template').get(pk=campaign_id)
        if campaign.status != 'SENDING': logger.warning(f"Celery task [ID: {self.request.id}]: Campaign {campaign_id} status is '{campaign.status}', not 'SENDING'. Aborting."); return f"Campaign {campaign_id} not in SENDING state."
        pending_recipients = CampaignContact.objects.filter(campaign=campaign, status='PENDING').select_related('contact')
        recipient_count = pending_recipients.count(); logger.info(f"Celery task [ID: {self.request.id}]: Found {recipient_count} pending recipients for campaign {campaign_id}.")
        if recipient_count == 0: logger.info(f"Celery task [ID: {self.request.id}]: No pending recipients for campaign {campaign_id}. Marking completed."); campaign.status = 'COMPLETED'; campaign.completed_at = timezone.now(); campaign.save(update_fields=['status', 'completed_at']); return f"Campaign {campaign_id} completed (no pending recipients)."
        queued_count = 0
        for recipient in pending_recipients.iterator():
            try:
                # --- TODO: Implement proper component formatting ---
                formatted_components = campaign.template.components # Placeholder
                send_whatsapp_message_task.delay(recipient_wa_id=recipient.contact.wa_id, message_type='template', template_name=campaign.template.name, components=formatted_components, campaign_contact_id=recipient.id)
                queued_count += 1
            except Exception as e: logger.error(f"Celery task [ID: {self.request.id}]: Failed to queue message for recipient {recipient.contact.wa_id} (CC ID: {recipient.id}) in campaign {campaign_id}: {e}"); recipient.status = 'FAILED'; recipient.error_message = f"Failed to queue send task: {e}"; recipient.save(update_fields=['status', 'error_message'])
        logger.info(f"Celery task [ID: {self.request.id}]: Queued {queued_count} send tasks for campaign {campaign_id}.")
        campaign.status = 'COMPLETED'; campaign.completed_at = timezone.now(); campaign.save(update_fields=['status', 'completed_at']); logger.info(f"Celery task [ID: {self.request.id}]: Marked campaign {campaign_id} as COMPLETED after queueing.")
        return f"Campaign {campaign_id}: Queued {queued_count} messages."
    except MarketingCampaign.DoesNotExist: logger.error(f"Celery task [ID: {self.request.id}]: Campaign ID {campaign_id} not found."); return f"Campaign ID {campaign_id} not found."
    except Exception as exc:
        logger.exception(f"Celery task [ID: {self.request.id}]: Unexpected error during bulk send for campaign {campaign_id}.");
        try: MarketingCampaign.objects.filter(pk=campaign_id).update(status='FAILED')
        except Exception as update_e: logger.error(f"Celery task [ID: {self.request.id}]: Also failed to update campaign {campaign_id} status to FAILED: {update_e}")
        raise self.retry(exc=exc)

