from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('ebooks/', views.ebook_list_view, name='list'),
    path('ebooks/<slug:slug>/', views.ebook_detail_view, name='detail'),
    path('categoria/<slug:slug>/', views.category_view, name='category'),
]