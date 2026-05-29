from django.urls import path
from . import views

app_name = 'delivery'

urlpatterns = [
    path('download/<uuid:token>/', views.download_ebook, name='download'),
    path('download/<uuid:token>/bonus/<int:bonus_id>/', views.download_bonus, name='download_bonus'),
]