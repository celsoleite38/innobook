from django.contrib import admin
from .models import DownloadToken, DownloadLog


class DownloadLogInline(admin.TabularInline):
    model         = DownloadLog
    extra         = 0
    readonly_fields = ['ip_address', 'user_agent', 'downloaded_at']
    can_delete    = False


@admin.register(DownloadToken)
class DownloadTokenAdmin(admin.ModelAdmin):
    list_display  = [
        'token', 'get_ebook', 'get_buyer',
        'downloads', 'max_downloads', 'remaining_downloads',
        'is_active', 'expires_at'
    ]
    list_filter   = ['is_active']
    readonly_fields = [
        'token', 'downloads', 'last_download_at',
        'last_ip', 'created_at', 'remaining_downloads',
        'is_expired', 'is_valid'
    ]
    search_fields = [
        'token', 'order__buyer__email',
        'order__ebook__title'
    ]
    inlines = [DownloadLogInline]

    fieldsets = (
        ('Token', {
            'fields': ('token', 'order', 'is_active')
        }),
        ('Controle de Downloads', {
            'fields': (
                'downloads', 'max_downloads',
                'remaining_downloads', 'last_download_at', 'last_ip'
            )
        }),
        ('Expiração', {
            'fields': ('expires_at', 'is_expired', 'is_valid')
        }),
        ('Datas', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='eBook')
    def get_ebook(self, obj):
        return obj.order.ebook.title

    @admin.display(description='Comprador')
    def get_buyer(self, obj):
        return obj.order.buyer_email


@admin.register(DownloadLog)
class DownloadLogAdmin(admin.ModelAdmin):
    list_display  = ['get_ebook', 'ip_address', 'downloaded_at']
    readonly_fields = ['token', 'ip_address', 'user_agent', 'downloaded_at']
    search_fields = ['token__order__ebook__title', 'ip_address']

    @admin.display(description='eBook')
    def get_ebook(self, obj):
        return obj.token.order.ebook.title