import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


def _is_sandbox():
    return 'sandbox' in settings.ASAAS_URL


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
    # CPF do perfil; em sandbox permite CPF fictício
    cpf_limpo = ''.join(filter(str.isdigit, getattr(user, 'cpf', '') or ''))

    if not cpf_limpo or cpf_limpo == '00000000000':
        if not _is_sandbox():
            raise Exception('CPF é obrigatório. Preencha no perfil.')
        cpf_limpo = '00000000000'

    if not _is_sandbox() and cpf_limpo != '00000000000':
        from apps.accounts.validators import cpf_valido
        if not cpf_valido(cpf_limpo):
            raise Exception('CPF inválido. Verifique o CPF no seu perfil.')

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
        if not customer.get('cpfCnpj') and cpf_limpo != '00000000000':
            put_resp = requests.put(
                _url(f'/customers/{customer_id}'),
                headers=_headers(),
                json={
                    'name': user.get_full_name() or user.username,
                    'email': user.email,
                    'cpfCnpj': cpf_limpo,
                }
            )
            if put_resp.status_code != 200:
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


def create_charge(order, billing_type, ip=None, value=None):
    """
    Cria a cobrança no Asaas. NUNCA recebe dados de cartão aqui — para cartão
    de crédito o Asaas devolve `invoiceUrl` (checkout hospedado) e o cliente
    paga na página segura do Asaas.

    `value` (opcional) permite cobrar um total que não é o amount do pedido —
    usado no carrinho: soma dos produtos + fretes.
    """
    customer_id = get_or_create_customer(order.buyer)

    payload = {
        'customer': customer_id,
        'billingType': billing_type,
        'value': float(value) if value is not None else float(order.amount),
        'dueDate': _due_date(billing_type),
        'description': f'BookHub — {order.ebook.title} ({order.get_variant_display()})',
        'externalReference': str(order.order_id),
        'postalService': False,
    }

    if ip:
        payload['remoteIp'] = ip

    response = requests.post(_url('/payments'), headers=_headers(), json=payload)
    charge = response.json()

    if 'id' not in charge:
        raise Exception(f'Erro ao criar cobrança Asaas: {charge}')

    return charge


def refund_charge(charge_id, value=None):
    """
    Estorna uma cobrança no Asaas. `value` opcional permite estorno parcial
    (usado no cancelamento de frete físico — o produto + frete voltam juntos).
    """
    payload = {}
    if value is not None:
        payload['value'] = float(value)
    response = requests.post(
        _url(f'/payments/{charge_id}/refund'),
        headers=_headers(),
        json=payload,
    )
    data = response.json()
    if response.status_code >= 400:
        raise Exception(f'Erro ao estornar cobrança: {data}')
    return data


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
    else:  # PIX e CREDIT_CARD
        due = agora_local + timedelta(hours=25)  # Garante que é amanhã
    return due.strftime('%Y-%m-%d')
