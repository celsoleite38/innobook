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

    cpf_limpo = ''.join(filter(str.isdigit, user.cpf or ''))

    if not cpf_limpo:
        raise Exception(
            'CPF é obrigatório para realizar pagamentos. '
            'Acesse seu perfil e preencha o CPF.'
        )

    # Busca cliente existente
    response = requests.get(
        _url('/customers'),
        headers=_headers(),
        params={'email': user.email}
    )
    data = response.json()

    if data.get('data'):
        customer    = data['data'][0]
        customer_id = customer['id']

        # CPF vazio no Asaas → atualiza
        if not customer.get('cpfCnpj'):
            try:
                put_resp = requests.post(
                    _url(f'/customers/{customer_id}'),
                    headers=_headers(),
                    json={
                        'name'    : user.get_full_name() or user.username,
                        'email'   : user.email,
                        'cpfCnpj' : cpf_limpo,
                    }
                )
                result = put_resp.json()
                print(f'Atualização CPF: {result}')

                # Se POST não funcionou, deleta e recria
                if 'id' not in result:
                    del_resp = requests.delete(
                        _url(f'/customers/{customer_id}'),
                        headers=_headers()
                    )
                    print(f'Cliente deletado: {del_resp.status_code}')

                    new_resp = requests.post(
                        _url('/customers'),
                        headers=_headers(),
                        json={
                            'name'               : user.get_full_name() or user.username,
                            'email'              : user.email,
                            'cpfCnpj'            : cpf_limpo,
                            'notificationDisabled': False,
                        }
                    )
                    new_customer = new_resp.json()
                    print(f'Novo cliente: {new_customer}')

                    if 'id' not in new_customer:
                        raise Exception(f'Erro ao recriar cliente: {new_customer}')

                    return new_customer['id']

            except Exception as e:
                print(f'Erro ao atualizar CPF: {e}')
                raise

        return customer_id

    # Cliente não existe — cria novo
    payload = {
        'name'               : user.get_full_name() or user.username,
        'email'              : user.email,
        'cpfCnpj'            : cpf_limpo,
        'notificationDisabled': False,
    }
    response = requests.post(
        _url('/customers'),
        headers=_headers(),
        json=payload
    )
    customer = response.json()
    print(f'Novo cliente criado: {customer}')

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