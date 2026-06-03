from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    list_display  = [
        'username', 'email', 'get_full_name',
        'role_badge', 'is_active', 'date_joined'
    ]
    list_filter   = ['role', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering      = ['-date_joined']

    # Adiciona o campo role nos fieldsets do UserAdmin padrão
    fieldsets = UserAdmin.fieldsets + (
        ('Perfil InnoBook', {
            'fields': ('role', 'bio', 'avatar', 'cpf')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Perfil InnoBook', {
            'fields': ('role', 'cpf')
        }),
    )

    @admin.display(description='Tipo')
    def role_badge(self, obj):
        from django.utils.html import format_html
        if obj.role == 'producer':
            return (' Escritor')
        return (' Comprador' )