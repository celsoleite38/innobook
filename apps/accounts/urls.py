from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views
from .forms import PasswordResetForm

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('2fa/', views.two_factor_view, name='two_factor'),
    path('verificar-email/<uidb64>/<token>/', views.verify_email_view, name='verify_email'),
    path('reenviar-verificacao/', views.resend_verification_view, name='resend_verification'),
    path('solicitar-produtor/', views.request_producer_view, name='request_producer'),
    path('senha/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        form_class=PasswordResetForm,
        email_template_name='emails/password_reset_email.txt',
        html_email_template_name='emails/password_reset_email.html',
        subject_template_name='emails/password_reset_subject.txt',
        success_url=reverse_lazy('accounts:password_reset_done'),
    ), name='password_reset'),
    path('senha/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html',
    ), name='password_reset_done'),
    path('senha/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url=reverse_lazy('accounts:password_reset_complete'),
    ), name='password_reset_confirm'),
    path('senha/concluido/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),
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

    # Painel de Administração — Gestão de Usuários
    path('admin-painel/usuarios/', views.admin_users_list_view, name='admin_users'),
    path('admin-painel/usuarios/<int:pk>/', views.admin_user_detail_view, name='admin_user_detail'),
    path('admin-painel/usuarios/<int:pk>/toggle-access/', views.admin_toggle_access_view, name='admin_toggle_access'),
    path('admin-painel/usuarios/<int:pk>/toggle-writer/', views.admin_toggle_writer_view, name='admin_toggle_writer'),
]
