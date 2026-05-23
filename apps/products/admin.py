from django.contrib import admin
from .models import Category, Ebook


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


@admin.register(Ebook)
class EbookAdmin(admin.ModelAdmin):
    list_display   = ['title', 'author', 'category', 'price', 'status', 'featured', 'created_at']
    list_filter    = ['status', 'category', 'featured', 'language']
    search_fields  = ['title', 'author__username', 'description']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['created_at', 'updated_at']
    list_editable  = ['status', 'featured']

    fieldsets = (
        ('Informações Básicas', {
            'fields': ('title', 'slug', 'author', 'category', 'description')
        }),
        ('Arquivos', {
            'fields': ('cover', 'file', 'preview')
        }),
        ('Preços', {
            'fields': ('price', 'discount_price')
        }),
        ('Detalhes', {
            'fields': ('pages', 'language', 'status', 'featured')
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at', 'published_at'),
            'classes': ('collapse',)
        }),
    )