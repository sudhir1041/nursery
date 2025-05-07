# whatsapp_app/urls.py
from django.urls import path
from . import views # Import views from the current app

app_name = 'whatsapp_app' # Make sure app_name is defined

urlpatterns = [
    # Existing URLs...
    path('', views.dashboard, name='whatsapp_index'), # Changed view to dashboard
    path('settings/', views.whatsapp_settings_view, name='settings'),
    path('chats/', views.chat_list, name='chat_list'),
    path('chats/<str:wa_id>/', views.chat_detail, name='chat_detail'),
    path('contacts/add/', views.add_new_contact, name='add_contact'),

    # Bot URLs
    path('bots/', views.bot_response_list, name='bot_list'),
    path('bots/create/', views.bot_response_create, name='bot_response_create'),
    path('bots/<int:pk>/edit/', views.bot_response_update, name='bot_response_edit'),
    path('bots/<int:pk>/delete/', views.bot_response_delete, name='bot_response_delete'),
    path('autoreply/', views.autoreply_settings_view, name='autoreply_settings'),

    # Marketing Campaign URLs
    path('marketing/campaigns/', views.campaign_list, name='campaign_list'),
    path('marketing/campaigns/create/', views.campaign_create, name='campaign_create'),
    path('marketing/campaigns/<int:pk>/', views.campaign_detail, name='campaign_detail'),
    path('marketing/campaigns/<int:pk>/delete/', views.campaign_delete, name='campaign_delete'),
    path('marketing/campaigns/<int:pk>/upload/', views.upload_contacts_for_campaign, name='upload_contacts'),
    path('marketing/campaigns/<int:pk>/schedule/', views.schedule_campaign, name='schedule_campaign'),
    path('marketing/campaigns/<int:pk>/cancel/', views.cancel_campaign, name='cancel_campaign'),

    # Marketing Template URLs
    path('marketing/templates/', views.template_list, name='template_list'),
    path('marketing/templates/sync/', views.sync_whatsapp_templates, name='sync_templates'),

    # --- NEW: Webhook Handler URL ---
    path('webhook/', views.webhook_handler, name='webhook_handler'),

    # --- NEW: AJAX URLs for Chat ---
    path('api/messages/send/', views.send_manual_message_ajax, name='send_manual_message_ajax'),
    path('api/messages/latest/', views.get_latest_messages_ajax, name='get_latest_messages_ajax'),
    path('api/media/upload/', views.upload_whatsapp_media_ajax, name='whatsapp_media_upload_ajax'),

]
