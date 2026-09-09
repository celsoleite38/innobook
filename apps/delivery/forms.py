from django import forms
from .models import ShippingProfile


BR_STATES = {
    '': 'Selecione...',
    'AC': 'AC — Acre',
    'AL': 'AL — Alagoas',
    'AP': 'AP — Amapá',
    'AM': 'AM — Amazonas',
    'BA': 'BA — Bahia',
    'CE': 'CE — Ceará',
    'DF': 'DF — Distrito Federal',
    'ES': 'ES — Espírito Santo',
    'GO': 'GO — Goiás',
    'MA': 'MA — Maranhão',
    'MT': 'MT — Mato Grosso',
    'MS': 'MS — Mato Grosso do Sul',
    'MG': 'MG — Minas Gerais',
    'PA': 'PA — Pará',
    'PB': 'PB — Paraíba',
    'PR': 'PR — Paraná',
    'PE': 'PE — Pernambuco',
    'PI': 'PI — Piauí',
    'RJ': 'RJ — Rio de Janeiro',
    'RN': 'RN — Rio Grande do Norte',
    'RS': 'RS — Rio Grande do Sul',
    'RO': 'RO — Rondônia',
    'RR': 'RR — Roraima',
    'SC': 'SC — Santa Catarina',
    'SP': 'SP — São Paulo',
    'SE': 'SE — Sergipe',
    'TO': 'TO — Tocantins',
}


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
            'state': forms.Select(choices=list(BR_STATES.items())),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.REQUIRED_FIELDS:
            self.fields[field_name].required = True

    def clean_state(self):
        return self.cleaned_data.get('state', '').upper()

    def clean_zipcode(self):
        zipcode = self.cleaned_data.get('zipcode', '').replace('.', '').replace('-', '')
        if zipcode and not zipcode.isdigit():
            raise forms.ValidationError('CEP deve conter apenas números.')
        return zipcode
