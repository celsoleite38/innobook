import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

def _headers():
    if not settings.ASAAS_API_KEY:
        raise Exception('ASAAS_API_KEY não configurada no.env')
    return {
        'access_token': settings.ASAAS_API_KEY,
        'Content-Type': 'application/json',
    }

def _url(path):
    return f'{settings.ASAAS_URL}{path}'

def get_or_create_customer(user):
    # Pega CPF do perfil. Se não tiver, usa um fake pra sandbox
    cpf = getattr(user, 'cpf', '') or '00000000000'
    cpf_limpo = ''.join(filter(str.isdigit, cpf))

    if cpf_limpo == '00000000000' and 'sandbox' not in settings.ASAAS_URL:
        raise Exception('CPF é obrigatório. Preencha no perfil.')

    # Busca cliente existente
    response = requests.get(
        _url('/customers'),
        headers=_headers(),
        params={'email': user.email}
    )
    data = response.json()

    if data.get('data'):
        customer = data['data'][0]
        customer_id = customer['id']

        # CPF vazio no Asaas → atualiza com PUT
        if not customer.get('cpfCnpj') and cpf_limpo!= '00000000000':
            put_resp = requests.put( # PUT não POST
                _url(f'/customers/{customer_id}'),
                headers=_headers(),
                json={
                    'name': user.get_full_name() or user.username,
                    'email': user.email,
                    'cpfCnpj': cpf_limpo,
                }
            )
            if put_resp.status_code!= 200:
                print(f'Erro ao atualizar CPF: {put_resp.text}')

        return customer_id

    # Cliente não existe — cria novo
    payload = {
        'name': user.get_full_name() or user.username,
        'email': user.email,
        'cpfCnpj': cpf_limpo,
        'notificationDisabled': False,
    }
    response = requests.post(_url('/customers'), headers=_headers(), json=payload)
    customer = response.json()

    if 'id' not in customer:
        raise Exception(f'Erro ao criar cliente no Asaas: {customer}')

    return customer['id']

def create_charge(order, billing_type, card_data=None):
    customer_id = get_or_create_customer(order.buyer)

    payload = {
        'customer': customer_id,
        'billingType': billing_type,
        'value': float(order.amount),
        'dueDate': _due_date(billing_type),
        'description': f'BookHub — {order.ebook.title}',
        'externalReference': str(order.order_id),
        'postalService': False,
    }

    if billing_type == 'CREDIT_CARD' and card_data:
        payload['creditCard'] = {
            'holderName': card_data.get('holder_name'),
            'number': card_data.get('number'),
            'expiryMonth': card_data.get('expiry_month'),
            'expiryYear': card_data.get('expiry_year'),
            'ccv': card_data.get('ccv'),
        }
        payload['creditCardHolderInfo'] = {
            'name': order.buyer_name,
            'email': order.buyer_email,
            'cpfCnpj': card_data.get('cpf', ''),
            'postalCode': card_data.get('postal_code', ''),
            'addressNumber': card_data.get('address_number', ''),
            'phone': card_data.get('phone', ''),
        }

    response = requests.post(_url('/payments'), headers=_headers(), json=payload)
    charge = response.json()

    if 'id' not in charge:
        raise Exception(f'Erro ao criar cobrança Asaas: {charge}')

    return charge

def get_charge(charge_id):
    response = requests.get(_url(f'/payments/{charge_id}'), headers=_headers())
    return response.json()

def get_pix_qrcode(charge_id):
    response = requests.get(_url(f'/payments/{charge_id}/pixQrCode'), headers=_headers())
    return response.json()

def _due_date(billing_type):
    agora_local = timezone.localtime()
    if billing_type == 'BOLETO':
        due = agora_local + timedelta(days=3)
    else: # PIX e CREDIT_CARD
        due = agora_local + timedelta(hours=25) # Garante que é amanhã
    return due.strftime('%Y-%m-%d')
