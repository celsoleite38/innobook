from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    
    path('checkout/<int:ebook_id>/',     views.checkout_view,  name='checkout'),
    path('checkout/carrinho/', views.cart_checkout_view, name='cart_checkout'),
    path('checkout/cotar-frete/', views.shipping_quote_view, name='shipping_quote'),

    path('pix/check/<str:charge_id>/',   views.check_pix_view, name='check_pix'),

    path('success/<uuid:order_id>/',     views.success_view,   name='success'),
    path('pending/<uuid:order_id>/',     views.pending_view,   name='pending'),
    path('failed/',                      views.failed_view,    name='failed'),
    path('meus-pedidos/', views.my_orders_view, name='my_orders'),
    path('meus-pedidos/<uuid:order_id>/cancelar-envio/', views.order_cancel_shipping_view, name='order_cancel_shipping'),
   
    path('webhook/asaas/',               views.asaas_webhook,  name='webhook'),
        
    path('admin-painel/saques/',           views.admin_withdraws_view,      name='admin_withdraws'),
    path('admin-painel/saques/<int:pk>/',  views.admin_withdraw_detail_view,name='admin_withdraw_detail'),

    path('admin-painel/comissoes/', views.admin_commissions_view, name='admin_commissions'),
    path('admin-painel/envios/', views.admin_shipping_view, name='admin_shipping'),
]