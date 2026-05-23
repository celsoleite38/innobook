from django.contrib import admin
from .models import Order, Payment


class PaymentInline(admin.TabularInline):
    model  = Payment
    extra  = 0
    readonly_fields = ['method', 'amount', 'raw_response', 'created_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = [
        'order_id', 'buyer_name', 'ebook',
        'amount', 'status', 'gateway', 'created_at'
    ]
    list_filter   = ['status', 'gateway']
    search_fields = ['buyer_name', 'buyer_email', 'gateway_order_id']
    readonly_fields = [
        'order_id', 'platform_fee', 'producer_amount',
        'created_at', 'updated_at', 'paid_at'
    ]
    inlines = [PaymentInline]

    fieldsets = (
        ('Identificação', {
            'fields': ('order_id', 'status')
        }),
        ('Comprador', {
            'fields': ('buyer', 'buyer_name', 'buyer_email')
        }),
        ('Produto', {
            'fields': ('ebook',)
        }),
        ('Valores', {
            'fields': ('amount', 'platform_fee', 'producer_amount')
        }),
        ('Gateway', {
            'fields': ('gateway', 'gateway_order_id', 'gateway_payment_id')
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at', 'paid_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ['order', 'method', 'amount', 'created_at']
    list_filter   = ['method']
    readonly_fields = ['created_at']