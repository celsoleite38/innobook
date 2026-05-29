from django import forms
from .models import Ebook, EbookBonus


class EbookForm(forms.ModelForm):
    class Meta:
        model  = Ebook
        fields = [
            'title', 'description', 'category',
            'cover', 'file', 'file_epub', 'file_mobi',
            'preview', 'price', 'discount_price',
            'pages', 'language',
        ]
        widgets = {
           'title'         : forms.TextInput(attrs={'class': 'form-control'}),
            'description'   : forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'category'      : forms.Select(attrs={'class': 'form-select'}),
            'cover'         : forms.FileInput(attrs={'class': 'form-control'}),
            'file'          : forms.FileInput(attrs={'class': 'form-control'}),
            'file_epub'     : forms.FileInput(attrs={'class': 'form-control'}),
            'file_mobi'     : forms.FileInput(attrs={'class': 'form-control'}),
            'preview'       : forms.FileInput(attrs={'class': 'form-control'}),
            'price'         : forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'discount_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'pages'         : forms.NumberInput(attrs={'class': 'form-control'}),
            'language'      : forms.TextInput(attrs={'class': 'form-control'}),
        }

class EbookBonusForm(forms.ModelForm):
    class Meta:
        model  = EbookBonus
        fields = ['title', 'description', 'cover', 'file', 'file_epub', 'file_mobi', 'order']
        widgets = {
            'title'      : forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'cover'      : forms.FileInput(attrs={'class': 'form-control'}),
            'file'       : forms.FileInput(attrs={'class': 'form-control'}),
            'file_epub'  : forms.FileInput(attrs={'class': 'form-control'}),
            'file_mobi'  : forms.FileInput(attrs={'class': 'form-control'}),
            'order'      : forms.NumberInput(attrs={'class': 'form-control'}),
        }