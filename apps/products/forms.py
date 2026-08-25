from decimal import Decimal

from django import forms
from .models import Ebook, EbookBonus, PRECO_MINIMO
from .validators import validar_ebook, validar_imagem, validar_preview


class SafeClearableFileInput(forms.ClearableFileInput):
    """
    ClearableFileInput que nunca acessa .url do arquivo atual — o storage
    protegido levanta erro ao pedir URL pública. Mostra apenas o nome do
    arquivo atual e a opção de limpar/substituir.
    """

    template_name = 'widgets/clearable_file_input.html'

    def is_initial(self, value):
        return bool(value and getattr(value, 'name', None))


class EbookForm(forms.ModelForm):
    class Meta:
        model  = Ebook
        fields = [
            'title', 'description', 'category',
            'cover', 'file', 'file_epub', 'file_mobi',
            'preview',             'price', 'discount_price',
            'isbn_physical', 'isbn_pdf', 'isbn_epub', 'isbn_mobi',
            'physical_price', 'combo_price', 'physical_stock',
            'physical_weight_g', 'physical_length_cm',
            'physical_width_cm', 'physical_height_cm',
            'pages', 'language',
        ]
        widgets = {
           'title'         : forms.TextInput(attrs={'class': 'form-control'}),
            'description'   : forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'category'      : forms.Select(attrs={'class': 'form-select'}),
            'cover'         : SafeClearableFileInput(attrs={'class': 'form-control'}),
            'file'          : SafeClearableFileInput(attrs={'class': 'form-control'}),
            'file_epub'     : SafeClearableFileInput(attrs={'class': 'form-control'}),
            'file_mobi'     : SafeClearableFileInput(attrs={'class': 'form-control'}),
            'preview'       : SafeClearableFileInput(attrs={'class' : 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/*'}),
            'price'         : forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': str(PRECO_MINIMO)}),
            'discount_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': str(PRECO_MINIMO)}),
            'isbn_physical' : forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000-0-00-000000-0', 'maxlength': '13'}),
            'isbn_pdf'      : forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000-0-00-000000-0', 'maxlength': '13'}),
            'isbn_epub'     : forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000-0-00-000000-0', 'maxlength': '13'}),
            'isbn_mobi'     : forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000-0-00-000000-0', 'maxlength': '13'}),
            'physical_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': str(PRECO_MINIMO)}),
            'combo_price'   : forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': str(PRECO_MINIMO)}),
            'physical_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'physical_weight_g': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'physical_length_cm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'physical_width_cm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'physical_height_cm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'pages'         : forms.NumberInput(attrs={'class': 'form-control'}),
            'language'      : forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ('physical_stock', 'physical_weight_g',
                      'physical_length_cm', 'physical_width_cm',
                      'physical_height_cm',
                      'isbn_physical', 'isbn_pdf', 'isbn_epub', 'isbn_mobi',
                      'file', 'price'):
            self.fields[campo].required = False

    def clean(self):
        dados = super().clean()
        padroes = {
            'physical_stock': 0,
            'physical_weight_g': 300,
            'physical_length_cm': 16,
            'physical_width_cm': 16,
            'physical_height_cm': 2,
        }
        for campo, valor in padroes.items():
            if dados.get(campo) is None:
                dados[campo] = valor

        # Pelo menos um formato deve ser oferecido
        has_digital = bool(dados.get('file') or dados.get('file_epub') or dados.get('file_mobi'))
        has_physical = bool(dados.get('physical_price'))
        if not has_digital and not has_physical:
            raise forms.ValidationError(
                'Envie pelo menos um arquivo digital (PDF, EPUB ou MOBI) '
                'ou informe o preço físico.'
            )

        preco = dados.get('price')
        promocional = dados.get('discount_price')
        if preco is not None and promocional is not None and promocional >= preco:
            self.add_error(
                'discount_price',
                'O preço promocional deve ser menor que o preço normal.',
            )
        return dados

    def clean_file(self):
        arquivo = self.cleaned_data.get('file')
        validar_ebook(arquivo)
        return arquivo

    def clean_file_epub(self):
        arquivo = self.cleaned_data.get('file_epub')
        validar_ebook(arquivo)
        return arquivo

    def clean_file_mobi(self):
        arquivo = self.cleaned_data.get('file_mobi')
        validar_ebook(arquivo)
        return arquivo

    def clean_cover(self):
        arquivo = self.cleaned_data.get('cover')
        validar_imagem(arquivo)
        return arquivo

    def clean_preview(self):
        arquivo = self.cleaned_data.get('preview')
        validar_preview(arquivo)
        return arquivo

    @staticmethod
    def _validate_isbn(value):
        if not value:
            return
        value = value.strip()
        clean = value.replace('-', '')
        if len(clean) != 13 or not clean.isdigit():
            raise forms.ValidationError('ISBN deve ter exatamente 13 dígitos (ex: 978-65-00-00000-0).')
        return value

    def clean_isbn_physical(self):
        return self._validate_isbn(self.cleaned_data.get('isbn_physical'))

    def clean_isbn_pdf(self):
        return self._validate_isbn(self.cleaned_data.get('isbn_pdf'))

    def clean_isbn_epub(self):
        return self._validate_isbn(self.cleaned_data.get('isbn_epub'))

    def clean_isbn_mobi(self):
        return self._validate_isbn(self.cleaned_data.get('isbn_mobi'))


class EbookBonusForm(forms.ModelForm):
    class Meta:
        model  = EbookBonus
        fields = ['title', 'description', 'cover', 'file', 'file_epub', 'file_mobi', 'order']
        widgets = {
            'title'      : forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'cover'      : SafeClearableFileInput(attrs={'class': 'form-control'}),
            'file'       : SafeClearableFileInput(attrs={'class': 'form-control'}),
            'file_epub'  : SafeClearableFileInput(attrs={'class': 'form-control'}),
            'file_mobi'  : SafeClearableFileInput(attrs={'class': 'form-control'}),
            'order'      : forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def clean_file(self):
        arquivo = self.cleaned_data.get('file')
        validar_ebook(arquivo)
        return arquivo

    def clean_file_epub(self):
        arquivo = self.cleaned_data.get('file_epub')
        validar_ebook(arquivo)
        return arquivo

    def clean_file_mobi(self):
        arquivo = self.cleaned_data.get('file_mobi')
        validar_ebook(arquivo)
        return arquivo

    def clean_cover(self):
        arquivo = self.cleaned_data.get('cover')
        validar_imagem(arquivo)
        return arquivo