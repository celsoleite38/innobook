from django.contrib import admin
from .models import Category, Ebook, EbookBonus


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']

class EbookBonusInline(admin.StackedInline):
    model       = EbookBonus
    extra       = 1
    fields      = [
        'title', 'description', 'cover',
        'file', 'file_epub', 'file_mobi', 'order'
    ]


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
    class Media:
        js = ('js/validar_tamanho.js',)

@admin.register(EbookBonus)
class EbookBonusAdmin(admin.ModelAdmin):
    list_display  = ['title', 'ebook', 'order', 'get_formats']
    list_filter   = ['ebook']
    search_fields = ['title', 'ebook__title']

    @admin.display(description='Formatos')
    def get_formats(self, obj):
        return ' | '.join(obj.get_available_formats()) or '—'
    
    class Media:
        js = ('js/validar_tamanho.js',)