from django import forms
from .models import ProducerBankData, WithdrawRequest


class BankDataForm(forms.ModelForm):
    class Meta:
        model  = ProducerBankData
        fields = ['pix_type', 'pix_key', 'full_name']
        widgets = {
            'pix_type' : forms.Select(attrs={'class': 'form-select'}),
            'pix_key'  : forms.TextInput(attrs={
                'class'      : 'form-control',
                'placeholder': 'Digite sua chave PIX'
            }),
            'full_name': forms.TextInput(attrs={
                'class'      : 'form-control',
                'placeholder': 'Nome comp. titular+banco(ex:José da Silva - Nubank)'
            }),
        }


class WithdrawForm(forms.Form):
    amount = forms.DecimalField(
        label='Valor do saque (R$)',
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step' : '0.01',
            'min'  : '0',
        })
    )

class WithdrawReceiptForm(forms.ModelForm):
    """Form para o admin fazer upload do comprovante."""
    class Meta:
        model  = WithdrawRequest
        fields = ['receipt', 'note', 'status']
        widgets = {
            'receipt': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'note'   : forms.Textarea(attrs={
                'class'      : 'form-control',
                'rows'       : 3,
                'placeholder': 'Observação opcional...'
            }),
            'status' : forms.Select(attrs={'class': 'form-select'}),
        }