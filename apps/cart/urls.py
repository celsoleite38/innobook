from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path('',                        views.cart_view,        name='cart'),
    path('add/<int:ebook_id>/',     views.add_to_cart,      name='add'),
    path('remove/<int:item_id>/',   views.remove_from_cart, name='remove'),
    path('count/',                  views.cart_count,       name='count'),
]