from django.urls import path
from . import views

app_name = 'delivery'

urlpatterns = [
    path('download/<uuid:token>/', views.download_ebook, name='download'),
    path('download/<uuid:token>/bonus/<int:bonus_id>/', views.download_bonus, name='download_bonus'),

    # Painel do escritor — envios
    path('envios/', views.shipping_panel_view, name='shipping_panel'),
    path('envios/remetente/', views.shipping_profile_view, name='shipping_profile'),
    path('envios/oauth/', views.oauth_start, name='oauth_start'),
    path('envios/oauth/callback/', views.oauth_callback, name='oauth_callback'),
    path('envios/editora/oauth/', views.editora_oauth_start, name='editora_oauth_start'),
    path('envios/<int:pk>/etiqueta/', views.shipping_generate_label, name='shipping_generate_label'),
    path('envios/<int:pk>/enviado/', views.shipping_mark_shipped, name='shipping_mark_shipped'),
    path('envios/<int:pk>/cancelar/', views.shipping_cancel, name='shipping_cancel'),

    # Webhook Melhor Envios
    path('webhooks/melhor-envios/', views.melhor_envios_webhook, name='melhor_envios_webhook'),
]
