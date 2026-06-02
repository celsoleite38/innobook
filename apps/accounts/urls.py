from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('producer/',       views.producer_dashboard_view, name='producer'),
    path('producer/financeiro/',                     views.financial_view,       name='financial'),
    path('producer/saque/',                          views.withdraw_request_view,name='withdraw'),
    path('producer/ebook/new/',        views.ebook_create_view, name='ebook_create'),
    path('producer/ebook/<int:pk>/edit/', views.ebook_edit_view, name='ebook_edit'),
    path('producer/ebook/<int:pk>/bonus/',      views.bonus_list_view,   name='ebook_bonuses'),
    path('producer/ebook/<int:ebook_pk>/bonus/new/', views.bonus_create_view, name='bonus_create'),
    path('producer/bonus/<int:pk>/delete/',     views.bonus_delete_view, name='bonus_delete'),
]