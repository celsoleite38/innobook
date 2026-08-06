from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    list_display  = [
        'username', 'email', 'get_full_name',
        'role_badge', 'email_verified', 'producer_approved',
        'is_active', 'date_joined'
    ]
    list_filter   = ['role', 'producer_approved', 'producer_requested',
                     'email_verified', 'two_factor_enabled', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering      = ['-date_joined']

    # Adiciona o campo role nos fieldsets do UserAdmin padrão
    fieldsets = UserAdmin.fieldsets + (
        ('Perfil InnoBook', {
            'fields': ('role', 'bio', 'avatar', 'cpf')
        }),
        ('Segurança', {
            'fields': ('email_verified', 'two_factor_enabled')
        }),
        ('Produtor', {
            'fields': ('producer_requested', 'producer_approved')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Perfil InnoBook', {
            'fields': ('role', 'cpf')
        }),
    )

    actions = ['approve_producer', 'reject_producer']

    @admin.display(description='Tipo')
    def role_badge(self, obj):
        from django.utils.html import mark_safe
        if obj.role == 'producer':
            return mark_safe('<span style="color:#a07830;">Escritor</span>')
        return 'Comprador'

    @admin.action(description='Aprovar como produtor')
    def approve_producer(self, request, queryset):
        updated = queryset.update(
            role=User.PRODUCER,
            producer_approved=True,
            producer_requested=False,
        )
        self.message_user(request, f'{updated} usuário(s) aprovado(s) como produtor.')

    @admin.action(description='Rejeitar solicitação de produtor')
    def reject_producer(self, request, queryset):
        updated = queryset.update(
            producer_approved=False,
            producer_requested=False,
        )
        self.message_user(request, f'Solicitação rejeitada para {updated} usuário(s).')
