from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('checkout/<int:ebook_id>/',     views.checkout_view,  name='checkout'),
    path('success/<uuid:order_id>/',     views.success_view,   name='success'),
    path('pending/<uuid:order_id>/',     views.pending_view,   name='pending'),
    path('failed/',                      views.failed_view,    name='failed'),
    path('pix/check/<str:charge_id>/',   views.check_pix_view, name='check_pix'),
    path('webhook/asaas/',               views.asaas_webhook,  name='webhook'),
    path('checkout/carrinho/', views.cart_checkout_view, name='cart_checkout'),
    path('meus-pedidos/', views.my_orders_view, name='my_orders'),
]