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