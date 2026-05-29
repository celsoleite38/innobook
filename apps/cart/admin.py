from django.contrib import admin
from .models import Cart, CartItem

class CartItemInline(admin.TabularInline):
    model  = CartItem
    extra  = 0
    readonly_fields = ['ebook', 'added_at']

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'count', 'total', 'updated_at']
    inlines      = [CartItemInline]