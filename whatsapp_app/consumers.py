import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Contact, ChatMessage
# Import the Celery task instead of the direct util
from .tasks import send_whatsapp_message_task
from django.utils import timezone
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.wa_id = self.scope['url_route']['kwargs']['wa_id']
        self.room_group_name = f'chat_{self.wa_id}'
        self.user = self.scope['user']

        if not self.user.is_authenticated or not self.user.is_staff:
            await self.close()
            return

        contact_exists = await self.check_contact_exists(self.wa_id)
        if not contact_exists:
             logger.warning(f"WebSocket connection rejected: Contact {self.wa_id} not found.")
             await self.close()
             return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        logger.info(f"WebSocket connected for chat {self.wa_id}, user {self.user.username}")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            logger.info(f"WebSocket disconnected for chat {self.wa_id}")

    # Receive message from WebSocket (Staff sending message)
    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_text = text_data_json.get('message')

            if not message_text or not self.user.is_authenticated or not self.user.is_staff:
                return

            # --- Trigger Celery task to send message ---
            logger.info(f"Queueing send task for message to {self.wa_id} from user {self.user.username}")
            send_whatsapp_message_task.delay(
                recipient_wa_id=self.wa_id,
                message_type='text',
                text_content=message_text
                # Pass other args if needed, e.g., sender_user_id=self.user.id
            )
            # --- OPTIONAL: Send an immediate "sending" confirmation back to *this* user ---
            # This provides instant feedback before the task runs and broadcasts the actual result
            await self.send(text_data=json.dumps({
                'type': 'message_sending', # Custom type for JS to handle
                'text': message_text # Echo the text back
            }))

        except json.JSONDecodeError:
            logger.warning("Received invalid JSON over WebSocket")
            await self.send_error("Invalid message format received.")
        except Exception as e:
            logger.exception(f"Error receiving/processing WebSocket message: {e}")
            await self.send_error("An internal error occurred.")

    # Receive message broadcast from room group
    async def chat_message(self, event):
        message_data = event['message']
        # Send message down to the connected browser
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': message_data
        }))
        # logger.debug(f"Sent message {message_data.get('message_id')} down WebSocket for {self.wa_id}")

    # Helper to send error messages back to the client
    async def send_error(self, message_text):
         await self.send(text_data=json.dumps({
             'type': 'error',
             'message': message_text
         }))

    # Database Interaction Helpers (remain the same)
    @database_sync_to_async
    def check_contact_exists(self, wa_id):
        return Contact.objects.filter(wa_id=wa_id).exists()
