import requests
from django.conf import settings


# ── Helpers ────────────────────────────────────────────────

def _headers():
    return {
        'access_token': settings.ASAAS_API_KEY,
        'Content-Type': 'application/json',
    }


def _url(path):
    return f'{settings.ASAAS_URL}{path}'


# ── Clientes ───────────────────────────────────────────────

def get_or_create_customer(user):
    """
    Busca ou cria um cliente no Asaas pelo email.
    Retorna o customer_id do Asaas.
    """

    # Busca se já existe
    response = requests.get(
        _url('/customers'),
        headers=_headers(),
        params={'email': user.email}
    )
    data = response.json()

    if data.get('data'):
        customer = data['data'][0]

        # Atualiza CPF se ainda não tem
        if not customer.get('cpfCnpj') and user.cpf:
            cpf_limpo = user.cpf.replace('.', '').replace('-', '').strip()
            requests.put(
                _url(f"/customers/{customer['id']}"),
                headers=_headers(),
                json={'cpfCnpj': cpf_limpo}
            )

        return customer['id']

    # CPF obrigatório para criar
    if not user.cpf:
        raise Exception(
            'CPF é obrigatório para realizar pagamentos. '
            'Acesse seu perfil e preencha o CPF.'
        )

    cpf_limpo = user.cpf.replace('.', '').replace('-', '').strip()

    # Cria novo cliente
    payload = {
        'name' : user.get_full_name() or user.username,
        'email': user.email,
        'cpfCnpj': cpf_limpo,
        'notificationDisabled': False,
    }
    response = requests.post(
        _url('/customers'),
        headers=_headers(),
        json=payload
    )
    customer = response.json()

    if 'id' not in customer:
        raise Exception(f'Erro ao criar cliente no Asaas: {customer}')

    return customer['id']


# ── Cobranças ──────────────────────────────────────────────

def create_charge(order, billing_type, card_data=None):
    """
    Cria uma cobrança no Asaas.

    billing_type: 'PIX' | 'BOLETO' | 'CREDIT_CARD'
    card_data: dict com dados do cartão (apenas para CREDIT_CARD)

    Retorna o objeto completo da cobrança.
    """

    customer_id = get_or_create_customer(order.buyer)

    payload = {
        'customer'       : customer_id,
        'billingType'    : billing_type,
        'value'          : float(order.amount),
        'dueDate'        : _due_date(billing_type),
        'description'    : f'BookHub — {order.ebook.title}',
        'externalReference': str(order.order_id),
        'postalService'  : False,
    }

    # Dados do cartão
    if billing_type == 'CREDIT_CARD' and card_data:
        payload['creditCard'] = {
            'holderName'    : card_data.get('holder_name'),
            'number'        : card_data.get('number'),
            'expiryMonth'   : card_data.get('expiry_month'),
            'expiryYear'    : card_data.get('expiry_year'),
            'ccv'           : card_data.get('ccv'),
        }
        payload['creditCardHolderInfo'] = {
            'name'         : order.buyer_name,
            'email'        : order.buyer_email,
            'cpfCnpj'      : card_data.get('cpf', ''),
            'postalCode'   : card_data.get('postal_code', ''),
            'addressNumber': card_data.get('address_number', ''),
            'phone'        : card_data.get('phone', ''),
        }

    response = requests.post(
        _url('/payments'),
        headers=_headers(),
        json=payload
    )
    charge = response.json()

    if 'id' not in charge:
        raise Exception(f'Erro ao criar cobrança Asaas: {charge}')

    return charge


def get_charge(charge_id):
    """Busca uma cobrança pelo ID."""
    response = requests.get(
        _url(f'/payments/{charge_id}'),
        headers=_headers()
    )
    return response.json()


def get_pix_qrcode(charge_id):
    """Retorna o QR code PIX de uma cobrança."""
    response = requests.get(
        _url(f'/payments/{charge_id}/pixQrCode'),
        headers=_headers()
    )
    return response.json()


def get_boleto_pdf(charge_id):
    """Retorna a URL do PDF do boleto."""
    response = requests.get(
        _url(f'/payments/{charge_id}/identificationField'),
        headers=_headers()
    )
    return response.json()


# ── Utilitários ────────────────────────────────────────────

def _due_date(billing_type):
    """Define o vencimento conforme o método."""
    from django.utils import timezone
    from datetime import timedelta

    if billing_type == 'PIX':
        days = 1
    elif billing_type == 'BOLETO':
        days = 3
    else:
        days = 1

    due = timezone.now().date() + timedelta(days=days)
    return due.strftime('%Y-%m-%d')