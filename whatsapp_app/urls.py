# whatsapp_app/urls.py
from django.urls import path
from . import views # Import views from the current app

# Define the application namespace
app_name = 'whatsapp_app' # Renamed from whatsapp_integration

urlpatterns = [
    # --- Dashboard ---
    # URL: /whatsapp/dashboard/
     path('', views.dashboard, name='whatsapp_index'), 

    # --- Settings ---
    # URL: /whatsapp/settings/
    path('settings/', views.whatsapp_settings_view, name='settings'),

    # --- Webhook ---
    # URL: /whatsapp/webhook/ (Needs to match the URL given to Meta)
    path('webhook/receive-kVusV/', views.webhook_handler, name='webhook'),

    # --- Chat Interface ---
    # URL: /whatsapp/chats/
    path('chats/', views.chat_list, name='chat_list'),
    # URL: /whatsapp/chats/<contact_wa_id>/
    path('chats/<str:wa_id>/', views.chat_detail, name='chat_detail'),
    # URL: /whatsapp/chats/<contact_wa_id>/send/ (AJAX POST)
    path('chats/<str:wa_id>/send/', views.send_manual_message_ajax, name='send_manual_message_ajax'),
    # URL: /whatsapp/chats/messages/latest/ (AJAX GET)
    path('chats/messages/latest/', views.get_latest_messages_ajax, name='get_latest_messages_ajax'),

    # --- Marketing ---
    # URL: /whatsapp/marketing/campaigns/
    path('marketing/campaigns/', views.campaign_list, name='campaign_list'),
    # URL: /whatsapp/marketing/campaigns/new/
    path('marketing/campaigns/new/', views.campaign_create, name='campaign_create'),
    # URL: /whatsapp/marketing/campaigns/<campaign_id>/
    path('marketing/campaigns/<int:pk>/', views.campaign_detail, name='campaign_detail'),
    # URL: /whatsapp/marketing/campaigns/<campaign_id>/upload/ (POST)
    path('marketing/campaigns/<int:pk>/upload/', views.upload_contacts_for_campaign, name='campaign_upload_contacts'),
    # URL: /whatsapp/marketing/campaigns/<campaign_id>/schedule/ (POST)
    path('marketing/campaigns/<int:pk>/schedule/', views.schedule_campaign, name='campaign_schedule'),
    # URL: /whatsapp/marketing/campaigns/<campaign_id>/cancel/ (POST)
    path('marketing/campaigns/<int:pk>/cancel/', views.cancel_campaign, name='campaign_cancel'),

    path('marketing/campaigns/<int:pk>/delete/', views.campaign_delete, name='campaign_delete'),
    # URL: /whatsapp/marketing/templates/
    path('marketing/templates/', views.template_list, name='template_list'),
    # URL: /whatsapp/marketing/templates/sync/ (POST)
    path('marketing/templates/sync/', views.sync_whatsapp_templates, name='sync_templates'),
    

    # --- Bot/Auto-Reply Management (Optional - Add if using dedicated views) ---
    path('bots/', views.bot_response_list, name='bot_list'),
    path('bots/new/', views.bot_response_create, name='bot_response_create'),
    path('bots/<int:pk>/edit/', views.bot_response_update, name='bot_response_edit'),
    path('bots/<int:pk>/delete/', views.bot_response_delete, name='bot_response_delete'),
    path('autoreply/', views.autoreply_settings_view, name='autoreply_settings'),
]

# Example structure assumes these URLs are included in the main project urls.py like:
# path('whatsapp/', include('whatsapp_app.urls', namespace='whatsapp_app')),
