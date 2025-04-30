# whatsapp_app/tasks.py
from celery import shared_task, Task
from django.utils import timezone
from django.db import transaction, OperationalError
from django.db.models import Q
import time
import logging

# Import models and utils carefully to avoid circular imports if tasks are complex
# It's often safer to import within the task function if needed,
# but for models/utils used frequently, module-level is okay.
from .models import MarketingCampaign, CampaignContact, WhatsAppSettings
from .utils import send_whatsapp_message, get_active_whatsapp_settings

logger = logging.getLogger(__name__) # Use logger from settings

# --- Base Task with Retry Logic for Database Errors ---
class BaseWhatsappTask(Task):
    """Base Celery task with automatic retry for database OperationalError."""
    # Retry on database connection/locking issues
    autoretry_for = (OperationalError, )
    # Wait 5 seconds before first retry, then increase delay
    retry_kwargs = {'max_retries': 3, 'countdown': 5}
    # Use exponential backoff for subsequent retries
    retry_backoff = True
    retry_backoff_max = 60 # Maximum delay 60 seconds
    retry_jitter = True # Add random jitter to avoid thundering herd

# --- Bulk Campaign Sending Task ---
@shared_task(bind=True, base=BaseWhatsappTask) # Use bind=True to access self, base=BaseTask for retries
def send_bulk_campaign_messages_task(self, campaign_id: int):
    """
    Celery task to send messages for a specific marketing campaign.

    Iterates through pending recipients in batches and calls the send_whatsapp_message utility.
    Handles basic rate limiting and updates campaign/recipient status.

    Args:
        campaign_id: The primary key of the MarketingCampaign object.
    """
    task_id = self.request.id # Get Celery task ID for logging
    logger.info(f"[Task ID: {task_id}] Starting task send_bulk_campaign_messages for Campaign ID: {campaign_id}")
    try:
        # Fetch the campaign with related template for efficiency
        campaign = MarketingCampaign.objects.select_related('template').get(id=campaign_id)
    except MarketingCampaign.DoesNotExist:
        logger.warning(f"[Task ID: {task_id}] Campaign ID {campaign_id} not found. Task aborted.")
        return f"Campaign {campaign_id} not found."
    except OperationalError as db_exc:
         logger.warning(f"[Task ID: {task_id}] Database error fetching campaign {campaign_id}. Retrying task...")
         raise self.retry(exc=db_exc) # Retry using base task settings

    # --- Validate Campaign Status ---
    # Ensure the campaign should actually be sending
    if campaign.status not in ['SENDING', 'SCHEDULED']:
        logger.warning(f"[Task ID: {task_id}] Campaign {campaign_id} is in status '{campaign.status}', not 'SENDING' or 'SCHEDULED'. Task aborted.")
        return f"Campaign {campaign_id} not in a sendable state ({campaign.status})."

    # --- Mark as Sending if it was Scheduled ---
    if campaign.status == 'SCHEDULED':
         try:
             with transaction.atomic():
                 # Re-fetch campaign inside transaction to ensure atomicity if needed, or use select_for_update
                 campaign_to_update = MarketingCampaign.objects.select_for_update().get(id=campaign_id)
                 if campaign_to_update.status == 'SCHEDULED': # Double check status
                     campaign_to_update.status = 'SENDING'
                     if not campaign_to_update.started_at: # Set started_at only once
                         campaign_to_update.started_at = timezone.now()
                     campaign_to_update.save(update_fields=['status', 'started_at'])
                     campaign = campaign_to_update # Use the updated instance
                     logger.info(f"[Task ID: {task_id}] Marked campaign {campaign_id} as SENDING.")
                 else:
                      logger.warning(f"[Task ID: {task_id}] Campaign {campaign_id} status changed from SCHEDULED before update. Current: {campaign_to_update.status}. Aborting task.")
                      return f"Campaign {campaign_id} status changed from SCHEDULED."

         except OperationalError as db_exc:
              logger.warning(f"[Task ID: {task_id}] Database error updating campaign {campaign_id} status to SENDING. Retrying task...")
              raise self.retry(exc=db_exc)
         except MarketingCampaign.DoesNotExist: # Should not happen if fetched above, but safety check
              logger.error(f"[Task ID: {task_id}] Campaign {campaign_id} disappeared during status update. Task aborted.")
              return f"Campaign {campaign_id} not found during update."


    # --- Fetch Pending Recipients ---
    # Process recipients in batches to avoid loading too many into memory
    batch_size = 100 # Adjust batch size based on memory/performance
    # Query for recipients still marked as PENDING for this campaign
    pending_recipients_qs = CampaignContact.objects.filter(
        campaign=campaign,
        status='PENDING'
    ).select_related('contact') # Include contact data

    processed_in_batch = 0
    total_sent_successfully_in_task = 0 # Count successful API calls in this task run
    total_failed_in_task = 0 # Count failures during this task run
    # Rate limit delay (seconds) - adjust based on WhatsApp limits/recommendations (e.g., 1 message/sec)
    rate_limit_delay = 1.0

    logger.info(f"[Task ID: {task_id}] Campaign {campaign_id}: Found approx {pending_recipients_qs.count()} pending recipients. Processing in batches of {batch_size}.")

    # Loop through batches of pending recipients
    while True: # Keep processing batches until no pending recipients are found
        try:
            # Get the next batch using slicing
            batch = list(pending_recipients_qs[:batch_size])
        except OperationalError as db_exc:
             logger.warning(f"[Task ID: {task_id}] Database error fetching recipient batch for campaign {campaign_id}. Retrying task...")
             raise self.retry(exc=db_exc)

        if not batch:
            logger.info(f"[Task ID: {task_id}] Campaign {campaign_id}: No more pending recipients found in this iteration.")
            break # Exit the while loop if the batch is empty

        logger.info(f"[Task ID: {task_id}] Campaign {campaign_id}: Processing batch of {len(batch)} recipients.")
        processed_in_batch = 0 # Reset counter for this batch

        for recipient in batch:
            # Ensure we haven't processed this recipient in a concurrent task run (unlikely with batches but possible)
            if recipient.status != 'PENDING':
                 logger.warning(f"[Task ID: {task_id}] Recipient {recipient.pk} for campaign {campaign_id} status is '{recipient.status}', not PENDING. Skipping.")
                 continue

            try:
                # --- Construct Template Components for this recipient ---
                components_list = []
                template_structure = campaign.template.components # JSON field from template model
                variables = recipient.template_variables or {} # Variables stored for this contact

                # Validate template structure (should be a list of components)
                if not isinstance(template_structure, list):
                     logger.error(f"[Task ID: {task_id}] Campaign {campaign_id}, Recipient {recipient.pk}: Invalid template component structure (not a list): {template_structure}")
                     raise ValueError("Invalid template structure in DB")

                # Iterate through component specifications in the template structure
                for component_spec in template_structure:
                    component_type = component_spec.get('type', '').upper()
                    if not component_type: continue # Skip if type is missing

                    component_data = {"type": component_type} # Base for this component's payload
                    parameters = [] # Parameters for this specific component (e.g., body, header)

                    # --- Body Parameter Substitution ---
                    if component_type == 'BODY':
                        text_template = component_spec.get('text', '')
                        # Find expected variable placeholders like {{1}}, {{2}}
                        expected_var_indices = [str(i) for i in range(1, text_template.count('{{') + 1)]
                        for var_num_str in expected_var_indices:
                             # Get value from recipient's variables, default to empty string if missing
                             param_value = variables.get(var_num_str, '')
                             parameters.append({"type": "text", "text": str(param_value)}) # Ensure value is string

                    # --- Header Parameter Substitution (Example: TEXT Header) ---
                    elif component_type == 'HEADER' and component_spec.get('format') == 'TEXT':
                         text_template = component_spec.get('text', '')
                         # Header usually expects only one variable {{1}}
                         if '{{1}}' in text_template:
                              param_value = variables.get('1', '') # Get variable '1'
                              parameters.append({"type": "text", "text": str(param_value)})
                    # Add elif for other header formats (IMAGE, DOCUMENT, VIDEO) if needed
                    # elif component_type == 'HEADER' and component_spec.get('format') == 'IMAGE':
                    #     link = variables.get('header_image_url', '') # Get URL from variables
                    #     if link: parameters.append({"type": "image", "image": {"link": link}})

                    # --- Button Parameter Substitution (Example: URL Button with dynamic part) ---
                    elif component_type == 'BUTTONS':
                         buttons = component_spec.get('buttons', [])
                         button_params = [] # Params specific to this button component
                         for button_index, button_spec in enumerate(buttons):
                             if button_spec.get('type') == 'URL':
                                 url_template = button_spec.get('url', '')
                                 # Find the variable number expected in the URL suffix (usually '1')
                                 if '{{1}}' in url_template:
                                     # Get the corresponding variable value (e.g., from key 'button_url_1')
                                     # Define a clear convention for variable keys in your CSV/data source
                                     var_key = f"button_url_{button_index}_1" # Example key
                                     param_value = variables.get(var_key, '')
                                     # Parameter for URL button needs index and text payload
                                     button_params.append({
                                         "type": "text",
                                         "text": str(param_value) # The dynamic part of the URL suffix
                                     })
                         # Parameters for buttons are added at the component level, associated by index
                         if button_params:
                              # Note: The API structure for button parameters might differ slightly, check Meta docs.
                              # This assumes parameters map sequentially to buttons needing them.
                              component_data['parameters'] = button_params


                    # Add parameters list to the component data if parameters were generated
                    # Button parameters are handled within the 'BUTTONS' block above
                    if parameters and component_type != 'BUTTONS':
                         component_data['parameters'] = parameters

                    components_list.append(component_data)
                # --- End Component Construction ---


                # --- Prepare API Call Parameters ---
                message_params = {
                    'recipient_wa_id': recipient.contact.wa_id,
                    'message_type': 'template',
                    'template_name': campaign.template.name,
                    'template_language': campaign.template.language,
                    'template_components': components_list,
                }

                # --- Call the Sending Utility ---
                # This function handles the actual API call and initial logging
                message_obj = send_whatsapp_message(**message_params)

                # --- Update Recipient Status based on API call outcome ---
                # Check if send_whatsapp_message returned a valid message object with SENT status
                if message_obj and message_obj.message_id and message_obj.status == 'SENT':
                    recipient.status = 'SENT'
                    recipient.message_id = message_obj.message_id # Store the WAMID
                    recipient.sent_time = timezone.now()
                    recipient.error_message = None # Clear previous errors
                    total_sent_successfully_in_task += 1
                else:
                    # API call failed or didn't return WAMID (error logged in send_whatsapp_message/log_failed_message)
                    recipient.status = 'FAILED'
                    # Error message might be set by log_failed_message, or set a generic one
                    if not recipient.error_message:
                         recipient.error_message = "Failed during API send attempt (check util logs)."
                    total_failed_in_task += 1

                # Save recipient status within the loop (atomic update)
                try:
                     # Use atomic transaction for saving recipient status
                     with transaction.atomic():
                          recipient.save(update_fields=['status', 'message_id', 'sent_time', 'error_message'])
                except OperationalError as db_exc:
                     logger.warning(f"[Task ID: {task_id}] Database error saving recipient {recipient.pk} status for campaign {campaign_id}. Retrying task...")
                     raise self.retry(exc=db_exc) # Retry the whole task on DB error during save

                processed_in_batch += 1

                # --- Rate Limiting Delay ---
                time.sleep(rate_limit_delay) # Pause between messages

            except ValueError as e: # Catch errors during component construction etc.
                 logger.error(f"[Task ID: {task_id}] Data error processing recipient {recipient.pk} for campaign {campaign_id}: {e}")
                 recipient.status = 'FAILED'
                 recipient.error_message = f"Data processing error: {e}"[:500] # Truncate error
                 total_failed_in_task += 1
                 try:
                      with transaction.atomic():
                           recipient.save(update_fields=['status', 'error_message'])
                 except OperationalError as db_exc:
                      logger.warning(f"[Task ID: {task_id}] Database error saving FAILED recipient {recipient.pk} status for campaign {campaign_id}. Retrying task...")
                      raise self.retry(exc=db_exc)
                 processed_in_batch += 1 # Count as processed (failed)
            except Exception as e:
                 # Catch unexpected errors during processing a single recipient
                 logger.exception(f"[Task ID: {task_id}] Unexpected error processing recipient {recipient.pk} for campaign {campaign_id}: {e}")
                 recipient.status = 'FAILED'
                 recipient.error_message = f"Unexpected task error: {e}"[:500]
                 total_failed_in_task += 1
                 try:
                      with transaction.atomic():
                           recipient.save(update_fields=['status', 'error_message'])
                 except OperationalError as db_exc:
                      logger.warning(f"[Task ID: {task_id}] Database error saving FAILED recipient {recipient.pk} status for campaign {campaign_id}. Retrying task...")
                      raise self.retry(exc=db_exc)
                 processed_in_batch += 1 # Count as processed (failed)
                 # Optional: Add a small delay even after errors
                 time.sleep(rate_limit_delay / 2)


        logger.info(f"[Task ID: {task_id}] Campaign {campaign_id}: Finished processing batch. Processed this batch: {processed_in_batch}. Successful sends in task run: {total_sent_successfully_in_task}. Failed in task run: {total_failed_in_task}.")
        # Check if the batch processed was smaller than requested, indicating end of queue for this run
        if len(batch) < batch_size:
             logger.info(f"[Task ID: {task_id}] Campaign {campaign_id}: Last batch processed in this task run.")
             break # Exit while loop

    # --- Final Campaign Status Update ---
    # After processing all available batches in this task run, check overall campaign status
    try:
        # Re-fetch campaign to get latest status in case of concurrent updates (less likely with Celery)
        campaign.refresh_from_db()
        # Check if *any* recipients are *still* pending for this campaign
        # This accounts for cases where the task might restart or only process partial batches
        still_pending = CampaignContact.objects.filter(campaign=campaign, status='PENDING').exists()
        final_status = campaign.status # Keep current status unless changing

        if not still_pending and campaign.status == 'SENDING':
            # No more pending recipients AND campaign is marked as SENDING
            # Campaign is now completed (potentially with failures)
            # Check if there were any failures *at all* during the campaign's entire run
            any_failures_ever = CampaignContact.objects.filter(campaign=campaign, status='FAILED').exists()
            final_status = 'FAILED' if any_failures_ever else 'COMPLETED'
            campaign.completed_at = timezone.now()
            campaign.status = final_status
            # Use atomic transaction for final update
            with transaction.atomic():
                campaign.save(update_fields=['status', 'completed_at'])
            logger.info(f"[Task ID: {task_id}] Campaign '{campaign.name}' (ID: {campaign_id}) marked as {final_status}. Successful sends in task run: {total_sent_successfully_in_task}. Failed in task run: {total_failed_in_task}.")
        elif still_pending:
            # This case might happen if the task was interrupted/retried and didn't finish all batches
            logger.warning(f"[Task ID: {task_id}] Campaign {campaign_id} task finished but still has PENDING recipients. Status remains {campaign.status}.")
        else:
             # Campaign might already be COMPLETED/FAILED/CANCELLED from another run or action
             logger.info(f"[Task ID: {task_id}] Campaign {campaign_id} task finished. Current status is {campaign.status} (no update needed).")


        return f"Campaign {campaign_id} processing finished for this task run. Final Status: {final_status}. Sent in run: {total_sent_successfully_in_task}, Failed in run: {total_failed_in_task}."

    except OperationalError as db_exc:
         logger.warning(f"[Task ID: {task_id}] Database error during final status update for campaign {campaign_id}. Retrying task...")
         # This retry might re-process the last batch, ensure task logic is idempotent if possible
         raise self.retry(exc=db_exc)
    except Exception as final_err:
         logger.exception(f"[Task ID: {task_id}] Error during final status update for campaign {campaign_id}: {final_err}")
         # Don't retry here, just log the failure to update status
         return f"Campaign {campaign_id} processing finished but failed final status update. Check logs."


# --- Optional Task for Background CSV Processing ---
# @shared_task(base=BaseWhatsappTask)
# def process_uploaded_contacts_task(campaign_id: int, contacts_data: list):
#     """
#     Processes a list of contact data (from CSV) in the background.
#     Creates Contact and CampaignContact objects. Use for large uploads.
#     Args:
#         campaign_id: The ID of the MarketingCampaign.
#         contacts_data: A list of dictionaries, where each dict contains
#                        {'wa_id': '...', 'name': '...', 'variables': {...}}
#     """
#     logger.info(f"Starting background processing of {len(contacts_data)} contacts for campaign {campaign_id}")
#     try:
#         campaign = MarketingCampaign.objects.get(id=campaign_id)
#         added_count = 0
#         skipped_count = 0
#         # Use transaction.atomic for bulk creation efficiency and atomicity
#         with transaction.atomic():
#             for item in contacts_data:
#                 try:
#                     # Validate item data here if not done before sending to task
#                     if not item.get('wa_id'): continue
#
#                     contact, contact_created = Contact.objects.get_or_create(wa_id=item['wa_id'])
#                     if item.get('name') and (contact_created or contact.name != item['name']):
#                         contact.name = item['name']
#                         contact.save(update_fields=['name'])
#
#                     _, cc_created = CampaignContact.objects.get_or_create(
#                         campaign=campaign,
#                         contact=contact,
#                         defaults={'template_variables': item.get('variables')}
#                     )
#                     if cc_created:
#                         added_count += 1
#                     else:
#                         skipped_count += 1
#                 except Exception as item_err:
#                      logger.error(f"Error processing item {item} for campaign {campaign_id} in background task: {item_err}")
#                      # Decide whether to skip or fail the whole task based on error severity
#
#         logger.info(f"Finished background processing for campaign {campaign_id}. Added: {added_count}, Skipped: {skipped_count}")
#         # Optional: Update campaign status or notify user upon completion
#         # campaign.notes = f"CSV processed: Added {added_count}, Skipped {skipped_count}"
#         # campaign.save(update_fields=['notes'])
#         return f"Processed {added_count} new contacts, skipped {skipped_count} duplicates."
#
#     except MarketingCampaign.DoesNotExist:
#          logger.error(f"Campaign {campaign_id} not found during background contact processing.")
#          # Don't retry if campaign doesn't exist
#          return "Campaign not found."
#     except Exception as e:
#          logger.exception(f"Error during background contact processing for campaign {campaign_id}: {e}")
#          # Re-raise to potentially trigger Celery base task retries for DB errors etc.
#          raise
