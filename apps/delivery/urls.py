from django.urls import path
from . import views

app_name = 'delivery'

urlpatterns = [
    path('download/<uuid:token>/', views.download_ebook, name='download'),
]