from django import forms
from .models import ShippingProfile


class ShippingProfileForm(forms.ModelForm):
    # Obrigatórios para o Melhor Envios calcular frete e emitir etiqueta
    REQUIRED_FIELDS = [
        'full_name', 'document', 'phone', 'zipcode',
        'address', 'number', 'district', 'city', 'state',
    ]

    class Meta:
        model = ShippingProfile
        fields = [
            'full_name', 'document', 'phone', 'zipcode',
            'address', 'number', 'complement', 'district',
            'city', 'state',
        ]
        labels = {
            'full_name': 'Nome do remetente',
            'document': 'CPF/CNPJ',
            'phone': 'Telefone',
            'zipcode': 'CEP',
            'address': 'Endereço',
            'number': 'Número',
            'complement': 'Complemento',
            'district': 'Bairro',
            'city': 'Cidade',
            'state': 'UF',
        }
        widgets = {
            'state': forms.TextInput(attrs={'maxlength': '2'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.REQUIRED_FIELDS:
            self.fields[field_name].required = True

    def clean_zipcode(self):
        zipcode = self.cleaned_data.get('zipcode', '').replace('.', '').replace('-', '')
        if zipcode and not zipcode.isdigit():
            raise forms.ValidationError('CEP deve conter apenas números.')
        return zipcode
