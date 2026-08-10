"""
Cliente da API do Melhor Envios (OAuth2 + frete + etiquetas).

Endpoints usados (v2):
  - OAuth2 ......... GET  /oauth/authorize | POST /oauth/token
  - Cotação ........ POST /api/v2/me/shipment/calculate   (por produtos)
  - Carrinho ....... POST /api/v2/me/cart                  (por volume)
  - Compra ......... POST /api/v2/me/shipment/checkout     (debitar carteira)
  - Geração ........ POST /api/v2/me/shipment/generate
  - Impressão ...... POST /api/v2/me/shipment/print
  - Cancelamento ... POST /api/v2/me/shipment/cancel
  - Info ........... GET  /api/v2/me/shipment/{id}
"""
import hashlib
import hmac
import base64
import logging

import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .models import EditoraShippingAccount, ShippingProfile

logger = logging.getLogger(__name__)

USER_AGENT = f'BookHub ({settings.DEFAULT_FROM_EMAIL or "contato@bookhub.com.br"})'
TOKEN_TTL = timedelta(days=30)
REFRESH_GRACE = timedelta(days=1)  # renova 1 dia antes de expirar


class MelhorEnviosError(Exception):
    pass


def _url(path):
    return f'{settings.ME_URL}{path}'


# --------------------------------------------------------------------------- #
#  OAuth2                                                                      #
# --------------------------------------------------------------------------- #

def get_authorize_url(producer):
    """URL para o escritor autorizar o app no Melhor Envios."""
    from urllib.parse import urlencode
    params = {
        'client_id': settings.ME_CLIENT_ID,
        'redirect_uri': settings.ME_REDIRECT_URI,
        'response_type': 'code',
        'state': str(producer.id),
        'scope': settings.ME_API_SCOPES,
    }
    return _url('/oauth/authorize?') + urlencode(params)


def exchange_code(producer, code):
    """Troca o code de autorização por tokens e salva no perfil."""
    profile, _ = ShippingProfile.objects.get_or_create(producer=producer)
    resp = requests.post(
        _url('/oauth/token'),
        data={
            'grant_type': 'authorization_code',
            'client_id': settings.ME_CLIENT_ID,
            'client_secret': settings.ME_CLIENT_SECRET,
            'redirect_uri': settings.ME_REDIRECT_URI,
            'code': code,
        },
        headers={'User-Agent': USER_AGENT},
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or 'access_token' not in data:
        raise MelhorEnviosError(f'Erro ao trocar código: {data}')
    _save_tokens(profile, data)
    return profile


def refresh_token(profile):
    resp = requests.post(
        _url('/oauth/token'),
        data={
            'grant_type': 'refresh_token',
            'client_id': settings.ME_CLIENT_ID,
            'client_secret': settings.ME_CLIENT_SECRET,
            'refresh_token': profile.me_refresh_token,
        },
        headers={'User-Agent': USER_AGENT},
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or 'access_token' not in data:
        raise MelhorEnviosError(
            f'Falha ao renovar token do Melhor Envios: {data}'
        )
    _save_tokens(profile, data)


def _save_tokens(obj, data):
    obj.me_access_token = data['access_token']
    obj.me_refresh_token = data.get('refresh_token', obj.me_refresh_token)
    obj.me_expires_at = timezone.now() + TOKEN_TTL
    obj.save(update_fields=[
        'me_access_token', 'me_refresh_token', 'me_expires_at', 'updated_at'
    ])


def refresh_token(obj):
    """Renova o access_token de um ShippingProfile ou EditoraShippingAccount."""
    resp = requests.post(
        _url('/oauth/token'),
        data={
            'grant_type': 'refresh_token',
            'client_id': settings.ME_CLIENT_ID,
            'client_secret': settings.ME_CLIENT_SECRET,
            'refresh_token': obj.me_refresh_token,
        },
        headers={'User-Agent': USER_AGENT},
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or 'access_token' not in data:
        raise MelhorEnviosError(
            f'Falha ao renovar token do Melhor Envios: {data}'
        )
    _save_tokens(obj, data)


def get_token(producer):
    """
    Retorna o access_token a usar para o escritor.

    - uses_editora_account=True  (padrão) → token da conta da Editora.
    - uses_editora_account=False          → token da conta própria do escritor.
    """
    if not settings.ME_CLIENT_ID or not settings.ME_CLIENT_SECRET:
        raise MelhorEnviosError('Melhor Envios não configurado (falta .env).')

    profile = ShippingProfile.objects.filter(producer=producer).first()
    if profile and profile.uses_editora_account:
        return editora_token()

    if not profile or not profile.is_connected:
        raise MelhorEnviosError(
            'Conecte sua conta no Melhor Envios para vender livros físicos.'
        )
    if not profile.me_expires_at or \
            profile.me_expires_at < timezone.now() + REFRESH_GRACE:
        refresh_token(profile)
    return profile.me_access_token


# --------------------------------------------------------------------------- #
#  OAuth2 — conta da Editora                                                   #
# --------------------------------------------------------------------------- #
def editora_get_authorize_url():
    """URL para o administrador autorizar a conta da Editora no ME."""
    from urllib.parse import urlencode
    params = {
        'client_id': settings.ME_CLIENT_ID,
        'redirect_uri': settings.ME_REDIRECT_URI,
        'response_type': 'code',
        'state': 'editora',
        'scope': settings.ME_API_SCOPES,
    }
    return _url('/oauth/authorize?') + urlencode(params)


def editora_exchange_code(code):
    """Troca o code de autorização pelos tokens da conta da Editora."""
    account = EditoraShippingAccount.get()
    resp = requests.post(
        _url('/oauth/token'),
        data={
            'grant_type': 'authorization_code',
            'client_id': settings.ME_CLIENT_ID,
            'client_secret': settings.ME_CLIENT_SECRET,
            'redirect_uri': settings.ME_REDIRECT_URI,
            'code': code,
        },
        headers={'User-Agent': USER_AGENT},
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or 'access_token' not in data:
        raise MelhorEnviosError(f'Erro ao trocar código: {data}')
    _save_tokens(account, data)
    return account


def editora_token():
    """Access_token da conta da Editora (renova se necessário)."""
    if not settings.ME_CLIENT_ID or not settings.ME_CLIENT_SECRET:
        raise MelhorEnviosError('Melhor Envios não configurado (falta .env).')

    account = EditoraShippingAccount.get()
    if not account.is_connected:
        raise MelhorEnviosError(
            'A conta Melhor Envios da Editora ainda não foi conectada. '
            'Conecte em "Gestão de Envios" no painel administrativo.'
        )
    if not account.me_expires_at or \
            account.me_expires_at < timezone.now() + REFRESH_GRACE:
        refresh_token(account)
    return account.me_access_token


def shipping_ready_error(producer):
    """
    Retorna None se o escritor está pronto para envios físicos
    (remetente preenchido + conta de pagamento disponível),
    ou a mensagem de erro explicando o que falta.
    """
    profile = ShippingProfile.objects.filter(producer=producer).first()
    if not profile or not profile.has_origin_address:
        return 'Este escritor ainda não configurou o endereço de remetente.'
    if profile.uses_editora_account:
        if not EditoraShippingAccount.get().is_connected:
            return 'A conta Melhor Envios da Editora ainda não foi conectada.'
        return None
    if not profile.is_connected:
        return 'Este escritor ainda não conectou sua conta no Melhor Envios.'
    return None


def shipping_ready(producer):
    return shipping_ready_error(producer) is None


# --------------------------------------------------------------------------- #
#  Requisições autenticadas                                                    #
# --------------------------------------------------------------------------- #

def _request(method, path, producer, json=None, timeout=40):
    token = get_token(producer)
    resp = requests.request(
        method,
        _url(path),
        json=json,
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'User-Agent': USER_AGENT,
        },
        timeout=timeout,
    )
    try:
        data = resp.json()
    except ValueError:
        data = resp.text
    if resp.status_code >= 400:
        msg = data.get('message') if isinstance(data, dict) else data
        raise MelhorEnviosError(
            f'Melhor Envios ({resp.status_code}): {msg}'
        )
    return data


# --------------------------------------------------------------------------- #
#  Cotação de frete                                                            #
# --------------------------------------------------------------------------- #

def _digital(dims):
    """Arredonda para números inteiros como o ME exige."""
    return tuple(int(round(float(x))) for x in dims)


def calcular_frete(producer, origem_cep, destino_cep, items):
    """
    Cotação por produtos: o Melhor Envios calcula a embalagem somando
    múltiplos livros físicos do mesmo escritor.

    items: lista de dicts {ebook, quantity}
    """
    products = []
    for item in items:
        ebook = item['ebook']
        dims = ebook.physical_dimensions()
        if not dims:
            raise MelhorEnviosError(
                f'Preencha peso e dimensões do livro "{ebook.title}".'
            )
        length, width, height = _digital(dims[:3])
        weight_kg = dims[3] / 1000.0
        products.append({
            'id': str(ebook.id),
            'width': width,
            'height': height,
            'length': length,
            'weight': weight_kg,
            'insurance_value': float(item.get('unit_value') or ebook.physical_price),
            'quantity': item['quantity'],
        })

    payload = {
        'from': {'postal_code': origem_cep},
        'to': {'postal_code': destino_cep},
        'products': products,
        'options': {'receipt': False, 'own_hand': False},
    }
    data = _request('POST', '/api/v2/me/shipment/calculate', producer, json=payload)

    offers = []
    for offer in data if isinstance(data, list) else []:
        if not offer.get('id'):
            continue
        if offer.get('error'):
            continue
        price = float(offer.get('custom_price') or offer.get('price') or 0)
        if price <= 0:
            continue
        delivery = offer.get('custom_delivery_time') or offer.get('delivery_time') or 0
        packages = offer.get('packages') or []
        offers.append({
            'id': str(offer['id']),
            'name': offer.get('name', ''),
            'company_name': (offer.get('company') or {}).get('name', ''),
            'price': price,
            'delivery_time': delivery,
            'packages': packages,
        })
    return offers


def _estimate_volumes(items):
    """Volumes aproximados (fallback): soma peso, usa as maiores dimensões."""
    total_weight = 0
    length = width = height = 0
    insurance = 0.0
    for item in items:
        ebook = item['ebook']
        dims = ebook.physical_dimensions()
        if not dims:
            continue
        l, w, h = _digital(dims[:3])
        length = max(length, l)
        width = max(width, w)
        height = max(height, h)
        total_weight += dims[3] / 1000.0 * item['quantity']
        insurance += float(item.get('unit_value') or ebook.physical_price) * item['quantity']
    return [{
        'height': height or 2,
        'width': width or 16,
        'length': length or 16,
        'weight': round(total_weight or 0.3, 3),
        'insurance_value': round(insurance, 2),
    }]


# --------------------------------------------------------------------------- #
#  Compra de etiqueta                                                          #
# --------------------------------------------------------------------------- #

def _origin_payload(shipment):
    profile = shipment.producer.shipping_profile
    if not profile.has_origin_address:
        raise MelhorEnviosError(
            'Preencha os dados do remetente (painel do escritor).'
        )
    return {
        'name': profile.full_name,
        'phone': profile.phone,
        'email': settings.DEFAULT_FROM_EMAIL or '',
        'document': profile.document,
        'company_document': '',
        'state_register': 'ISENTO',
        'address': profile.address,
        'complement': profile.complement,
        'number': profile.number,
        'district': profile.district,
        'city': profile.city,
        'country_id': 'BR',
        'postal_code': profile.zipcode,
        'state_abbr': profile.state,
    }


def _destination_payload(order):
    return {
        'name': order.shipping_name,
        'phone': '',
        'email': order.buyer_email or '',
        'document': order.buyer.cpf if order.buyer else '',
        'company_document': '',
        'state_register': 'ISENTO',
        'address': order.shipping_address,
        'complement': order.shipping_complement,
        'number': order.shipping_number,
        'district': order.shipping_district,
        'city': order.shipping_city,
        'country_id': 'BR',
        'postal_code': order.shipping_zipcode,
        'state_abbr': order.shipping_state,
    }


def _items_payload(shipment):
    """Produtos declarados (nome + valor + quantidade) por pedido do pacote."""
    products = []
    for order in shipment.orders.all():
        qty = getattr(order, 'quantity', None) or 1
        products.append({
            'name': order.ebook.title,
            'quantity': qty,
            'unitary_value': float(order.amount),
        })
    return products


def gerar_etiqueta_completa(shipment):
    """
    Fluxo completo: insere no carrinho (1 chamada por volume) → checkout
    (debitar carteira do ME) → gera → imprime → salva dados no pacote.
    """
    orders = list(shipment.orders.all())
    if not orders:
        raise MelhorEnviosError('Pacote sem pedidos.')
    if not shipment.offer_id:
        raise MelhorEnviosError('Pacote sem oferta de frete selecionada.')

    origin = _origin_payload(shipment)
    destination = _destination_payload(orders[0])
    products = _items_payload(shipment)
    volumes = _estimate_volumes([
        {'ebook': o.ebook, 'quantity': getattr(o, 'quantity', 1) or 1,
         'unit_value': o.amount} for o in orders
    ])
    insurance_total = round(sum(v['insurance_value'] for v in volumes), 2)

    # Sem volumes confiáveis da oferta, usa estimativa própria
    packages = shipment.quote_payload.get('packages') or []
    if packages:
        volumes = [{
            'height': p.get('height') or 2,
            'width': p.get('width') or 16,
            'length': p.get('length') or 16,
            'weight': p.get('weight') or 0.3,
            'insurance_value': round(insurance_total / len(packages), 2),
        } for p in packages]

    order_ids = []
    for volume in volumes:
        payload = {
            'service': int(shipment.offer_id),
            'agency': None,
            'from': origin,
            'to': destination,
            'products': products,
            'volumes': [volume],
            'options': {
                'insurance_value': volume['insurance_value'],
                'receipt': False,
                'own_hand': False,
                'reverse': False,
                'non_commercial': True,
            },
        }
        data = _request('POST', '/api/v2/me/cart', shipment.producer, json=payload)
        order_id = data.get('id') if isinstance(data, dict) else None
        if not order_id:
            raise MelhorEnviosError(
                f'Erro ao inserir no carrinho do ME: {data}'
            )
        order_ids.append(order_id)
        _persist_from_cart(shipment, data)

    _request('POST', '/api/v2/me/shipment/checkout', shipment.producer,
             json={'orders': order_ids})
    _request('POST', '/api/v2/me/shipment/generate', shipment.producer,
             json={'orders': order_ids})

    print_resp = _request('POST', '/api/v2/me/shipment/print', shipment.producer,
                          json={'orders': order_ids, 'mode': 'public'})
    shipment.print_url = print_resp.get('url', '') if isinstance(print_resp, dict) else ''
    shipment.status = shipment.STATUS_READY
    shipment.save(update_fields=['print_url', 'status', 'updated_at'])
    shipment.sync_order_status()
    return shipment


def _persist_from_cart(shipment, data):
    """Grava id/protocolo/valores retornados ao inserir no carrinho."""
    if not shipment.melhor_envios_id:
        shipment.melhor_envios_id = str(data.get('id', ''))
        shipment.freight_cost = shipment.freight_cost or data.get('price', 0)
        shipment.carrier = shipment.carrier or (data.get('service') or {}).get('name', '')
        shipment.save(update_fields=[
            'melhor_envios_id', 'freight_cost', 'carrier', 'updated_at'
        ])


def cancelar_etiqueta(shipment, description='Pedido cancelado.'):
    """Cancela a etiqueta no ME (reason_id sempre 2)."""
    if not shipment.melhor_envios_id:
        raise MelhorEnviosError('Pacote ainda não tem etiqueta no Melhor Envios.')
    _request('POST', '/api/v2/me/shipment/cancel', shipment.producer, json={
        'order': {
            'id': shipment.melhor_envios_id,
            'reason_id': '2',
            'description': description,
        }
    })
    shipment.status = shipment.STATUS_CANCELLED
    shipment.save(update_fields=['status', 'updated_at'])
    shipment.sync_order_status()
    return shipment


def consultar_status(shipment):
    """Status atual da etiqueta no Melhor Envios."""
    if not shipment.melhor_envios_id:
        return None
    return _request(
        'GET', f'/api/v2/me/shipment/{shipment.melhor_envios_id}',
        shipment.producer
    )


# --------------------------------------------------------------------------- #
#  Webhook                                                                     #
# --------------------------------------------------------------------------- #

def verify_webhook_signature(body, signature):
    """HMAC-SHA256 (base64) do corpo usando o secret do app no ME.

    O Melhor Envios assina com o client_secret do aplicativo. Mantemos
    ME_WEBHOOK_TOKEN como override, caso queira uma chave diferente.
    """
    key = settings.ME_WEBHOOK_TOKEN or settings.ME_CLIENT_SECRET
    if not key or not signature:
        return False
    expected = base64.b64encode(
        hmac.new(
            key.encode(),
            body,
            hashlib.sha256,
        ).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


def map_webhook_event(event):
    """Mapeia evento do webhook para status interno do Shipment."""
    mapping = {
        'order.posted': 'shipped',
        'order.delivered': 'delivered',
        'order.cancelled': 'cancelled',
        'order.undelivered': 'cancelled',
    }
    return mapping.get(event)
