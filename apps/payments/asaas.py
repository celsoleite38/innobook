import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from payments.models import Payment

def _headers():
    """Headers padrão pra API do Asaas"""
    return {
        "access_token": settings.ASAAS_API_KEY,
        "Content-Type": "application/json"
    }

def _url(path):
    """Monta URL completa baseado no env"""
    return f"{settings.ASAAS_URL}{path}"

def _check_asaas_response(response, context="Asaas"):
    """Valida resposta do Asaas e levanta exceção com detalhe se der erro"""
    if response.status_code >= 400:
        try:
            error_data = response.json()
            errors = error_data.get('errors', [])
            error_msg = errors[0].get('description') if errors else response.text
        except:
            error_msg = response.text
        raise Exception(f"{context} error {response.status_code}: {error_msg}")
    return response.json()

def _due_date(billing_type):
    """Define vencimento usando timezone local -03:00"""
    agora_local = timezone.localtime()

    if billing_type == 'PIX':
        due = agora_local + timedelta(hours=25) # 25h = sempre amanhã
    elif billing_type == 'BOLETO':
        due = agora_local + timedelta(days=3)
    else:
        due = agora_local + timedelta(hours=25)

    return due.strftime('%Y-%m-%d')

def get_or_create_customer(user):
    """
    Busca cliente por CPF ou cria novo. Usa PUT pra atualizar.
    """
    cpf = (user.cpf or '').strip()
    if not cpf:
        raise ValueError("Usuário sem CPF")

    # 1. Busca por CPF
    response = requests.get(
        _url('/customers'),
        headers=_headers(),
        params={'cpfCnpj': cpf},
        timeout=30
    )
    search = _check_asaas_response(response, "Buscar cliente")
    existing_id = search['data'][0]['id'] if search.get('data') else None

    # 2. Monta payload
    payload = {
        "name": user.get_full_name() or user.username,
        "cpfCnpj": cpf,
        "email": user.email,
        "mobilePhone": (user.phone or '').strip(),
    }

    # 3. Atualiza com PUT se existe, senão cria com POST
    if existing_id:
        response = requests.put( # PUT pra atualizar, não POST
            _url(f'/customers/{existing_id}'),
            json=payload,
            headers=_headers(),
            timeout=30
        )
        customer = _check_asaas_response(response, "Atualizar cliente")
    else:
        response = requests.post(
            _url('/customers'),
            json=payload,
            headers=_headers(),
            timeout=30
        )
        customer = _check_asaas_response(response, "Criar cliente")

    # Salva no user
    user.asaas_customer_id = customer['id']
    user.save(update_fields=['asaas_customer_id'])
    return customer['id']

def create_charge(order, billing_type):
    """
    Cria cobrança no Asaas com dueDate correto
    """
    customer_id = get_or_create_customer(order.buyer)

    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": float(order.amount),
        "dueDate": _due_date(billing_type),
        "description": f"Pedido #{order.order_id}",
        "externalReference": str(order.order_id),
    }

    response = requests.post(
        _url('/payments'),
        json=payload,
        headers=_headers(),
        timeout=30
    )
    charge = _check_asaas_response(response, "Criar cobrança")

    # Atualiza ou cria Payment
    Payment.objects.update_or_create(
        order=order,
        defaults={
            "asaas_id": charge['id'],
            "status": charge['status'],
            "billing_type": billing_type,
            "amount": order.amount,
            "due_date": charge['dueDate']
        }
    )
    return charge

def get_pix_qrcode(charge_id):
    """Busca QR Code do Pix"""
    response = requests.get(
        _url(f'/payments/{charge_id}/pixQrCode'),
        headers=_headers(),
        timeout=30
    )
    return _check_asaas_response(response, "Buscar QR Code Pix")