from django.contrib import admin
from .models import (
    DownloadToken, DownloadLog, Shipment, ShippingProfile,
    EditoraShippingAccount,
)


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


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display  = ['id', 'producer', 'carrier', 'freight_cost', 'tracking_code', 'status', 'created_at']
    list_filter   = ['status', 'carrier']
    search_fields = ['producer__username', 'tracking_code', 'melhor_envios_id']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Pacote', {
            'fields': ('producer', 'buyer', 'status', 'carrier', 'delivery_time')
        }),
        ('Frete', {
            'fields': ('freight_cost', 'offer_id', 'quote_payload')
        }),
        ('Melhor Envios', {
            'fields': ('melhor_envios_id', 'tracking_code', 'tracking_url', 'label_pdf', 'print_url')
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at', 'posted_at', 'delivered_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ShippingProfile)
class ShippingProfileAdmin(admin.ModelAdmin):
    list_display  = ['producer', 'full_name', 'zipcode', 'city', 'state', 'is_connected', 'uses_editora_account', 'updated_at']
    list_filter   = ['uses_editora_account', 'state']
    search_fields = ['producer__username', 'full_name', 'zipcode']

    fieldsets = (
        ('Remetente', {
            'fields': (
                'full_name', 'document', 'phone',
                'zipcode', 'address', 'number', 'complement', 'district',
                'city', 'state'
            )
        }),
        ('Pagamento do frete', {
            'fields': ('uses_editora_account',),
            'description': (
                'Marcado (padrão): a conta Melhor Envios da Editora paga a '
                'postagem. Desmarcado: a conta própria do escritor paga.'
            )
        }),
        ('Conexão Melhor Envios', {
            'fields': (
                'me_access_token', 'me_refresh_token', 'me_expires_at'
            ),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(EditoraShippingAccount)
class EditoraShippingAccountAdmin(admin.ModelAdmin):
    list_display = ['id', 'holder_name', 'is_connected', 'me_expires_at', 'updated_at']
    readonly_fields = ['me_expires_at', 'updated_at']

    fieldsets = (
        ('Conta', {
            'fields': ('holder_name', 'is_connected')
        }),
        ('Tokens (OAuth2)', {
            'fields': ('me_access_token', 'me_refresh_token', 'me_expires_at'),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )