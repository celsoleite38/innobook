from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import construct_instance

from .models import Category, Ebook, EbookBonus
from core.storages import ProtectedFileSystemStorage

PROTECTED_FIELD_WIDGET = forms.FileInput(attrs={'class': 'form-control'})


def protected_formfield_widget(db_field, formfield):
    """Arquivos protegidos não têm URL — usa FileInput simples no admin."""
    if isinstance(getattr(db_field, 'storage', None), ProtectedFileSystemStorage):
        formfield.widget = PROTECTED_FIELD_WIDGET
    return formfield


class EbookChangelistForm(forms.ModelForm):
    """
    Formulário da edição rápida na listagem (list_editable).

    Valida apenas os campos editáveis (status/destaque). Erros apontados por
    Ebook.clean() para campos fora deste formulário (ex.: ISBN duplicado ou
    inválido) viram erro geral no topo da listagem, em vez de quebrar com
    ValueError ('EbookForm' has no field named ...).
    """

    class Meta:
        model = Ebook
        fields = ['status', 'featured']

    def _post_clean(self):
        opts = self._meta
        exclude = self._get_validation_exclusions()
        try:
            self.instance = construct_instance(
                self, self.instance, opts.fields, opts.exclude
            )
        except ValidationError as e:
            self._update_errors(e)
            return

        try:
            self.instance.full_clean(exclude=exclude, validate_unique=False)
        except ValidationError as e:
            for field, messages in e.error_dict.items():
                if field not in self.fields:
                    field = None  # exibe como erro geral no topo da listagem
                self.add_error(field, messages)


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

    def formfield_for_dbfield(self, db_field, **kwargs):
        return protected_formfield_widget(
            db_field, super().formfield_for_dbfield(db_field, **kwargs)
        )



@admin.register(Ebook)
class EbookAdmin(admin.ModelAdmin):
    list_display   = ['title', 'author', 'category', 'price', 'physical_price', 'status', 'featured', 'created_at']
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
            'fields': ('cover', 'file', 'file_epub', 'file_mobi', 'preview')
        }),
        ('Preços Digitais', {
            'fields': ('price', 'discount_price')
        }),
        ('ISBNs', {
            'fields': ('isbn_physical', 'isbn_pdf', 'isbn_epub', 'isbn_mobi'),
            'description': 'ISBNs por formato. Preencha o ISBN correspondente ao formato disponível.',
            'classes': ('collapse',)
        }),
        ('Livro Físico', {
            'fields': ('physical_price', 'combo_price', 'physical_stock',
                       'physical_weight_g', 'physical_length_cm',
                       'physical_width_cm', 'physical_height_cm'),
            'description': 'Preencha o preço físico e o estoque para oferecer a versão impressa. '
                           'Peso (g) e dimensões (cm) são usados na cotação do frete. '
                           'Combo = físico + digital; se vazio, usa a soma dos dois preços.'
        }),
        ('Detalhes', {
            'fields': ('pages', 'language', 'status', 'featured'),
        }),
        ('Rejeição', {
            'fields': ('rejection_reason',),
            'description': 'Justificativa enviada ao escritor quando o eBook é rejeitado '
                           '(usada pelo painel de moderação). Aprovar limpa este campo.',
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at', 'published_at'),
            'classes': ('collapse',)
        }),
    )

    class Media:
        js = ('js/validar_tamanho.js',)

    def get_changelist_form(self, request, **kwargs):
        """Edição rápida da listagem sem crash quando Ebook.clean() aponta
        erros em campos fora de status/destaque (ex.: ISBN)."""
        kwargs.setdefault('form', EbookChangelistForm)
        return super().get_changelist_form(request, **kwargs)

    def formfield_for_dbfield(self, db_field, **kwargs):
        return protected_formfield_widget(
            db_field, super().formfield_for_dbfield(db_field, **kwargs)
        )

@admin.register(EbookBonus)
class EbookBonusAdmin(admin.ModelAdmin):
    list_display  = ['title', 'ebook', 'order', 'get_formats']
    list_filter   = ['ebook']
    search_fields = ['title', 'ebook__title']

    @admin.display(description='Formatos')
    def get_formats(self, obj):
        return ' | '.join(obj.get_available_formats()) or '—'

    def formfield_for_dbfield(self, db_field, **kwargs):
        return protected_formfield_widget(
            db_field, super().formfield_for_dbfield(db_field, **kwargs)
        )
    
    class Media:
        js = ('js/validar_tamanho.js',)