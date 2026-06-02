from django.contrib import admin
from django.utils import timezone
from .models import Order, Payment, PlatformConfig, ProducerBankData, WithdrawRequest


class PaymentInline(admin.TabularInline):
    model       = Payment
    extra       = 0
    readonly_fields = ['method', 'amount', 'raw_response', 'created_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display    = ['order_id', 'buyer_name', 'ebook', 'amount', 'status', 'created_at']
    list_filter     = ['status', 'gateway']
    search_fields   = ['buyer_name', 'buyer_email', 'gateway_order_id']
    readonly_fields = ['order_id', 'platform_fee', 'producer_amount', 'created_at', 'updated_at', 'paid_at']
    inlines         = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ['order', 'method', 'amount', 'created_at']
    list_filter   = ['method']
    readonly_fields = ['created_at']


@admin.register(PlatformConfig)
class PlatformConfigAdmin(admin.ModelAdmin):
    list_display = ['commission_percent', 'min_withdraw', 'updated_at']

    def has_add_permission(self, request):
        # Só permite 1 registro
        return not PlatformConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProducerBankData)
class ProducerBankDataAdmin(admin.ModelAdmin):
    list_display  = ['producer', 'pix_type', 'pix_key', 'full_name', 'updated_at']
    search_fields = ['producer__username', 'pix_key']


@admin.register(WithdrawRequest)
class WithdrawRequestAdmin(admin.ModelAdmin):
    list_display   = ['producer', 'amount', 'pix_key', 'status', 'created_at', 'paid_at']
    list_filter    = ['status']
    search_fields  = ['producer__username', 'pix_key']
    readonly_fields = ['producer', 'amount', 'pix_key', 'pix_type', 'created_at']
    list_editable  = ['status']
    actions        = ['mark_as_paid', 'mark_as_rejected']

    fieldsets = (
        ('Solicitação', {
            'fields': ('producer', 'amount', 'pix_type', 'pix_key', 'status', 'note')
        }),
        ('Datas', {
            'fields': ('created_at', 'paid_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.action(description='Marcar como PAGO')
    def mark_as_paid(self, request, queryset):
        queryset.update(status=WithdrawRequest.STATUS_PAID, paid_at=timezone.now())
        self.message_user(request, f'{queryset.count()} saque(s) marcado(s) como pago.')

    @admin.action(description='Marcar como REJEITADO')
    def mark_as_rejected(self, request, queryset):
        queryset.update(status=WithdrawRequest.STATUS_REJECTED)
        self.message_user(request, f'{queryset.count()} saque(s) rejeitado(s).')