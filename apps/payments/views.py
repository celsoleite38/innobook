from urllib import request

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.conf import settings
from apps.products.models import Ebook
from apps.delivery.utils import create_download_token, get_client_ip
from .models import Order, Payment, WithdrawRequest
from .asaas import create_charge, get_charge, get_pix_qrcode
from .emails import send_purchase_confirmation, send_new_sale_notification
import json

from django.contrib.admin.views.decorators import staff_member_required
from functools import wraps
from django.core.paginator import Paginator
from .forms import WithdrawReceiptForm
from decimal import Decimal, ROUND_HALF_UP



# ── Checkout ───────────────────────────────────────────────

def _get_shipping_from_post(request):
    return {
        'shipping_name':       request.POST.get('shipping_name', '').strip(),
        'shipping_zipcode':    request.POST.get('shipping_zipcode', '').strip(),
        'shipping_address':    request.POST.get('shipping_address', '').strip(),
        'shipping_number':     request.POST.get('shipping_number', '').strip(),
        'shipping_district':   request.POST.get('shipping_district', '').strip(),
        'shipping_complement': request.POST.get('shipping_complement', '').strip(),
        'shipping_city':       request.POST.get('shipping_city', '').strip(),
        'shipping_state':      request.POST.get('shipping_state', '').strip(),
    }


def _shipping_is_valid(data):
    return all([data['shipping_name'], data['shipping_zipcode'],
                data['shipping_address'], data['shipping_number'],
                data['shipping_district'],
                data['shipping_city'], data['shipping_state']])


# ── Cotação de frete (livro físico) ─────────────────────────

def _group_cart_by_author(items):
    """Agrupa itens físicos do carrinho por escritor (1 pacote por escritor)."""
    from apps.products.models import FORMAT_PHYSICAL, FORMAT_COMBO
    groups = {}
    for item in items:
        if item.variant in (FORMAT_PHYSICAL, FORMAT_COMBO):
            groups.setdefault(item.ebook.author_id, []).append(item)
    return groups


@login_required
def shipping_quote_view(request):
    """Cotação AJAX do frete — agrupada por escritor (carrinho ou 1 livro)."""
    from apps.delivery.melhor_envios import (
        calcular_frete, shipping_ready_error, MelhorEnviosError,
    )
    from apps.products.models import FORMAT_PHYSICAL

    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido.'}, status=405)

    zipcode = request.POST.get('zipcode', '').strip()
    if len(zipcode) < 8:
        return JsonResponse({'error': 'Informe um CEP válido.'}, status=400)

    ebook_id = request.POST.get('ebook_id', '').strip()

    if ebook_id:
        # Checkout de livro único
        ebook = Ebook.objects.filter(id=ebook_id, status='published').first()
        if not ebook:
            return JsonResponse({'error': 'Livro não encontrado.'}, status=404)
        variant = request.POST.get('variant') or FORMAT_PHYSICAL
        normalized = {
            ebook.author_id: [{
                'variant': variant,
                'price': ebook.get_format_price(variant),
                'ebook': ebook,
            }]
        }
    else:
        cart = getattr(request.user, 'cart', None)
        if not cart or not cart.items.exists():
            return JsonResponse({'error': 'Carrinho vazio.'}, status=400)
        groups = _group_cart_by_author(cart.items.select_related(
            'ebook', 'ebook__author'
        ))
        normalized = {
            author_id: [
                {'variant': i.variant, 'price': i.price, 'ebook': i.ebook}
                for i in items
            ]
            for author_id, items in groups.items()
        }

    if not normalized:
        return JsonResponse({'error': 'Seu carrinho não tem livros físicos.'}, status=400)

    packages = []
    for author_id, items in normalized.items():
        author = items[0]['ebook'].author
        profile = getattr(author, 'shipping_profile', None)
        ready_error = shipping_ready_error(author)
        pkg = {
            'author_id':     author_id,
            'author_name':   author.get_full_name() or author.username,
            'connected':     ready_error is None,
            'origin_zipcode': profile.zipcode if profile else '',
            'offers':        [],
            'error':         ready_error or '',
        }
        if not ready_error:
            try:
                offers = calcular_frete(author, profile.zipcode, zipcode, [
                    {'ebook': item['ebook'], 'quantity': 1, 'unit_value': item['price']}
                    for item in items
                ])
                pkg['offers'] = offers
            except MelhorEnviosError as e:
                pkg['error'] = str(e)
            except Exception as e:
                pkg['error'] = f'Erro ao cotar frete: {e}'
        packages.append(pkg)

    return JsonResponse({'packages': packages})


@login_required
def checkout_view(request, ebook_id):
    from apps.products.models import FORMAT_DIGITAL, FORMAT_PHYSICAL, FORMAT_COMBO

    ebook = get_object_or_404(Ebook, id=ebook_id, status='published')

    variant = request.GET.get('variant') or request.POST.get('variant') or FORMAT_DIGITAL
    if variant not in (FORMAT_DIGITAL, FORMAT_PHYSICAL, FORMAT_COMBO):
        variant = FORMAT_DIGITAL
    if variant in (FORMAT_PHYSICAL, FORMAT_COMBO) and not ebook.has_physical():
        messages.warning(request, 'A versão física deste livro está esgotada.')
        return redirect('products:detail', slug=ebook.slug)

    # Já comprou esse formato?
    if ebook.user_owns_format(request.user, variant):
        messages.info(request, 'Você já possui esta versão deste eBook!')
        return redirect('accounts:dashboard')

    needs_shipping = variant in (FORMAT_PHYSICAL, FORMAT_COMBO)
    amount         = ebook.get_format_price(variant)
    shipping       = _get_shipping_from_post(request)
    freight        = Decimal('0')
    offer_choice   = None

    if needs_shipping and shipping['shipping_zipcode']:
        offer_choice = _build_single_offer(
            request, ebook, shipping['shipping_zipcode']
        )
        if offer_choice:
            freight = Decimal(str(offer_choice['price']))
        elif offer_choice is False:
            messages.error(
                request,
                'Selecione a transportadora para o frete do seu livro físico.'
            )

    if request.method == 'POST':
        if needs_shipping and not _shipping_is_valid(shipping):
            messages.error(
                request,
                'Preencha todos os dados de entrega do livro físico (incluindo bairro).'
            )
        elif needs_shipping and not offer_choice:
            messages.error(
                request,
                'Selecione a transportadora para o frete do seu livro físico.'
            )
        else:
            billing_type = request.POST.get('billing_type', 'PIX')

            # Cria pedido pendente
            order = Order.objects.create(
                buyer       = request.user,
                ebook       = ebook,
                variant     = variant,
                amount      = amount,
                status      = Order.STATUS_PENDING,
                gateway     = 'asaas',
                buyer_email = request.user.email,
                buyer_name  = request.user.get_full_name() or request.user.username,
                **shipping,
            )

            # Vincula o pacote físico (1 livro → 1 pacote)
            if needs_shipping and offer_choice:
                from apps.delivery.models import Shipment
                shipment = Shipment.objects.create(
                    producer      = ebook.author,
                    buyer         = request.user,
                    status        = Shipment.STATUS_AWAITING,
                    freight_cost  = freight,
                    offer_id      = offer_choice['id'],
                    carrier       = offer_choice['name'],
                    delivery_time = offer_choice.get('delivery_time') or 0,
                    quote_payload = {
                        'offer_id': offer_choice['id'],
                        'name': offer_choice['name'],
                        'packages': offer_choice.get('packages', []),
                    },
                )
                shipment.orders.set([order])
                order.shipping_cost = freight
                order.save(update_fields=['shipping_cost'])

            try:
                # Cria cobrança no Asaas (SEM dados de cartão — cartão vai para o
                # checkout hospedado do Asaas via invoiceUrl)
                charge = create_charge(
                    order, billing_type,
                    ip=get_client_ip(request),
                    value=order.total_with_shipping,
                )

                # Salva ID da cobrança
                order.gateway_order_id = charge['id']
                order.save()

                # Registra pagamento
                Payment.objects.create(
                    order        = order,
                    method       = billing_type.lower(),
                    amount       = order.total_with_shipping,
                    raw_response = charge,
                )

                # Cartão — checkout seguro do Asaas (o cliente paga na página deles)
                if billing_type == 'CREDIT_CARD':
                    return render(request, 'payments/card.html', {
                        'order'      : order,
                        'charge'     : charge,
                        'invoice_url': charge.get('invoiceUrl', ''),
                        'charge_id'  : charge['id'],
                    })

                # PIX — mostra QR code
                if billing_type == 'PIX':
                    pix = get_pix_qrcode(charge['id'])
                    return render(request, 'payments/pix.html', {
                        'order'     : order,
                        'pix'       : pix,
                        'charge_id' : charge['id'],
                    })

                # Boleto — mostra linha digitável
                if billing_type == 'BOLETO':
                    return render(request, 'payments/boleto.html', {
                        'order'     : order,
                        'charge'    : charge,
                    })

            except Exception as e:
                order.delete()
                erro = str(e)
                if 'CPF é obrigatório' in erro:
                    messages.warning(
                        request,
                        'Por favor, preencha seu CPF no perfil antes de comprar.'
                    )
                    return redirect('accounts:profile')
                messages.error(request, f'Erro ao processar pagamento: {erro}')
                return redirect('products:detail', slug=ebook.slug)

    return render(request, 'payments/checkout.html', {
        'ebook': ebook,
        'variant': variant,
        'amount': amount,
        'needs_shipping': needs_shipping,
        'shipping': shipping,
    })


def _build_single_offer(request, ebook, zipcode):
    """
    Valida a oferta escolhida no checkout de livro único (server-side).
    Retorna: dict(offer) se válida | False se inválida | None se não escolhida.
    """
    from apps.delivery.melhor_envios import (
        calcular_frete, shipping_ready_error, MelhorEnviosError,
    )

    chosen = request.POST.get('offer', '').strip()
    if not chosen:
        return None

    author = ebook.author
    profile = getattr(author, 'shipping_profile', None)
    ready_error = shipping_ready_error(author)
    if ready_error:
        messages.error(
            request,
            f'O escritor {author.get_full_name() or author.username} não está '
            f'pronto para envios físicos: {ready_error}'
        )
        return False

    try:
        offers = calcular_frete(author, profile.zipcode, zipcode, [
            {'ebook': ebook, 'quantity': 1, 'unit_value': ebook.get_format_price(request.POST.get('variant') or 'physical')}
        ])
    except MelhorEnviosError as e:
        messages.error(request, str(e))
        return False

    offer = next((o for o in offers if o['id'] == chosen), None)
    if not offer:
        messages.error(request, 'O frete escolhido expirou. Refaça a cotação.')
        return False
    return offer


# ── Verificar PIX (chamada AJAX da página PIX) ─────────────

@login_required
def check_pix_view(request, charge_id):
    """Verifica se o pagamento foi efetuado (polling do frontend)."""
    orders = Order.objects.filter(
        gateway_order_id=charge_id,
        buyer=request.user
    )

    if not orders.exists():
        return JsonResponse({'paid': False, 'status': 'not_found'})

    # Já confirmado?
    if orders.filter(status=Order.STATUS_PAID).exists():
        return JsonResponse({'paid': True, 'order_id': str(orders.first().order_id)})

    # Consulta o status REAL na API do Asaas (não confia no cliente)
    try:
        charge = get_charge(charge_id)
    except Exception as e:
        return JsonResponse({'paid': False, 'error': str(e)})

    if charge.get('status') in ('CONFIRMED', 'RECEIVED'):
        # Confirma TODOS os pedidos vinculados a esta cobrança (carrinho)
        for order in orders:
            if order.status != Order.STATUS_PAID:
                _confirm_order(order, charge_id)
        return JsonResponse({'paid': True, 'order_id': str(orders.first().order_id)})

    return JsonResponse({'paid': False, 'status': charge.get('status')})


# ── Success ────────────────────────────────────────────────

@login_required
def success_view(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, buyer=request.user)
    token = order.download_tokens.filter(is_active=True).first()
    return render(request, 'payments/success.html', {
        'order': order,
        'token': token,
    })


@login_required
def pending_view(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, buyer=request.user)
    return render(request, 'payments/pending.html', {'order': order})


@login_required
def failed_view(request, order_id=None):
    order = None
    if order_id:
        order = Order.objects.filter(
            order_id=order_id, buyer=request.user
        ).first()
        if order:
            order.status = Order.STATUS_FAILED
            order.save()
    return render(request, 'payments/failed.html', {'order': order})


# ── Webhook Asaas ──────────────────────────────────────────

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def asaas_webhook(request):
    # 1. Exige token configurado
    if not settings.ASAAS_WEBHOOK_TOKEN:
        logger.error("ASAAS_WEBHOOK_TOKEN não configurado. Webhook rejeitado.")
        return HttpResponse(status=503)

    # 2. Valida o token enviado pelo Asaas no header
    asaas_token = request.headers.get('asaas-access-token')
    if asaas_token != settings.ASAAS_WEBHOOK_TOKEN:
        logger.warning(f"Webhook com token inválido: {asaas_token}")
        return HttpResponse(status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Webhook Asaas com JSON inválido")
        return HttpResponse(status=400)

    event = data.get('event', '')
    payment = data.get('payment', {})

    if not payment:
        return JsonResponse({"status": "ignored"}, status=200)

    charge_id = payment.get('id')

    # Localiza TODOS os pedidos vinculados a esta cobrança
    # (carrinho compartilha o mesmo gateway_order_id)
    orders = Order.objects.filter(gateway_order_id=charge_id)

    if not orders.exists():
        external_reference = payment.get('externalReference')
        if external_reference:
            orders = Order.objects.filter(order_id=external_reference)

    if not orders.exists():
        logger.error(f"Pedido não encontrado no webhook: {charge_id}")
        return JsonResponse({"status": "order_not_found"}, status=200)

    # 3. Idempotência - se já está pago, só retorna 200
    if orders.filter(status=Order.STATUS_PAID).exists() and not orders.exclude(status=Order.STATUS_PAID).exists():
        logger.info(f"Cobrança {charge_id} já paga. Ignorando webhook duplicado.")
        return JsonResponse({"status": "already_paid"}, status=200)

    # 4. Processa eventos
    if event in ('PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED'):
        # Só confirma se a API do Asaas realmente confirmar (não confia no body)
        try:
            charge = get_charge(charge_id)
        except Exception as e:
            logger.error(f"Erro ao consultar cobrança na API: {e}")
            return JsonResponse({"status": "verify_failed"}, status=200)

        if charge.get('status') not in ('CONFIRMED', 'RECEIVED'):
            logger.warning(
                f"Webhook diz pago mas a API retornou {charge.get('status')}. Ignorando."
            )
            return JsonResponse({"status": "not_confirmed_by_api"}, status=200)

        for order in orders:
            if order.status != Order.STATUS_PAID:
                _confirm_order(order, charge_id)
        logger.info(f"Cobrança {charge_id} confirmada via webhook")

    elif event == 'PAYMENT_REFUNDED':
        for order in orders:
            order.status = Order.STATUS_REFUNDED
            order.save()
            order.download_tokens.update(is_active=False)
        logger.info(f"Cobrança {charge_id} estornada")

    elif event in ('PAYMENT_DELETED', 'PAYMENT_OVERDUE'):
        for order in orders:
            order.status = Order.STATUS_CANCELLED
            order.save()
        logger.info(f"Cobrança {charge_id} cancelada/vencida")

    # 5. Sempre retorna 200 pro Asaas não pausar
    return JsonResponse({"status": "received"}, status=200)


# ── Helper interno ─────────────────────────────────────────

def _confirm_order(order, charge_id):
    """Confirma pedido, gera token (digital/combo), baixa estoque e envia emails."""
    from apps.products.models import (
        FORMAT_DIGITAL, FORMAT_PHYSICAL, FORMAT_COMBO
    )

    order.status             = Order.STATUS_PAID
    order.gateway_payment_id = charge_id
    order.paid_at            = timezone.now()
    order.save()

    # Baixa estoque do livro físico
    if order.variant in (FORMAT_PHYSICAL, FORMAT_COMBO):
        ebook = order.ebook
        if ebook.physical_stock and ebook.physical_stock > 0:
            ebook.physical_stock -= 1
            ebook.save(update_fields=['physical_stock'])

    token = None
    if order.variant in (FORMAT_DIGITAL, FORMAT_COMBO):
        if not order.download_tokens.exists():
            token = create_download_token(order, days_valid=365, max_downloads=10)
        else:
            token = order.download_tokens.filter(is_active=True).first()

    try:
        send_purchase_confirmation(order, token)
        send_new_sale_notification(order)
    except Exception as e:
        print(f'Erro email: {e}')

@login_required
def cart_checkout_view(request):
    from apps.cart.models import Cart, CartItem
    from apps.products.models import FORMAT_PHYSICAL, FORMAT_COMBO
    from apps.delivery.models import Shipment
    from apps.delivery.melhor_envios import (
        calcular_frete, shipping_ready_error, MelhorEnviosError,
    )
    from decimal import Decimal, ROUND_HALF_UP

    try:
        cart = request.user.cart
    except Exception:
        messages.error(request, 'Carrinho vazio.')
        return redirect('cart:cart')

    items = list(cart.items.select_related('ebook', 'ebook__author'))

    if not items:
        messages.error(request, 'Seu carrinho está vazio.')
        return redirect('cart:cart')

    # Remove itens já comprados (por formato)
    items = [item for item in items if not item.ebook.user_owns_format(
        request.user, item.variant
    )]

    if not items:
        messages.info(request, 'Todos os itens já foram comprados!')
        return redirect('accounts:dashboard')

    total = sum(item.price for item in items)
    needs_shipping = any(
        item.variant in (FORMAT_PHYSICAL, FORMAT_COMBO) for item in items
    )

    shipping = _get_shipping_from_post(request)
    packages = []  # list(dict(author, items, offer)) — validado no POST

    if needs_shipping and shipping['shipping_zipcode']:
        packages, quote_errors = _build_packages_from_post(
            request, items, shipping['shipping_zipcode']
        )
    else:
        quote_errors = []

    if request.method == 'POST':
        if needs_shipping and not _shipping_is_valid(shipping):
            messages.error(
                request,
                'Preencha todos os dados de entrega do livro físico (incluindo bairro).'
            )
        elif needs_shipping and quote_errors:
            messages.error(request, ' '.join(quote_errors))
        else:
            billing_type = request.POST.get('billing_type', 'PIX')
            orders_criados = []
            order_map = {}

            try:
                for item in items:
                    order = Order.objects.create(
                        buyer       = request.user,
                        ebook       = item.ebook,
                        variant     = item.variant,
                        amount      = item.price,
                        status      = Order.STATUS_PENDING,
                        gateway     = 'asaas',
                        buyer_email = request.user.email,
                        buyer_name  = request.user.get_full_name() or request.user.username,
                        **shipping,
                    )
                    orders_criados.append(order)
                    order_map[item.id] = order

                # Frete: 1 pacote por escritor, fracionado entre os pedidos
                shipping_total = Decimal('0')
                for pkg in packages:
                    pkg_orders = [order_map[i.id] for i in pkg['items']]
                    shipment = Shipment.objects.create(
                        producer      = pkg['author'],
                        buyer         = request.user,
                        status        = Shipment.STATUS_AWAITING,
                        freight_cost  = Decimal(str(pkg['offer']['price'])),
                        offer_id      = pkg['offer']['id'],
                        carrier       = pkg['offer']['name'],
                        delivery_time = pkg['offer'].get('delivery_time') or 0,
                        quote_payload = {
                            'offer_id': pkg['offer']['id'],
                            'name': pkg['offer']['name'],
                            'packages': pkg['offer'].get('packages', []),
                        },
                    )
                    shipment.orders.set(pkg_orders)

                    freight = shipment.freight_cost
                    shipping_total += freight
                    split = (freight / len(pkg_orders)).quantize(
                        Decimal('0.01'), rounding=ROUND_HALF_UP
                    )
                    for i, order in enumerate(pkg_orders):
                        order.shipping_cost = (
                            freight - split * (len(pkg_orders) - 1)
                            if i == len(pkg_orders) - 1 else split
                        )
                        order.save(update_fields=['shipping_cost'])

                grand_total = Decimal(str(total)) + shipping_total

                # Cria UMA cobrança no Asaas com o total (produtos + fretes)
                order_ref = orders_criados[0]
                charge = create_charge(
                    order_ref, billing_type,
                    ip=get_client_ip(request),
                    value=grand_total,
                )

                # Salva charge_id em todos os pedidos
                for order in orders_criados:
                    order.gateway_order_id = charge['id']
                    order.save(update_fields=['gateway_order_id'])

                Payment.objects.create(
                    order        = order_ref,
                    method       = billing_type.lower(),
                    amount       = grand_total,
                    raw_response = charge,
                )

                # Limpa o carrinho
                cart.items.all().delete()

                # Cartão — checkout seguro do Asaas
                if billing_type == 'CREDIT_CARD':
                    return render(request, 'payments/card.html', {
                        'order'      : order_ref,
                        'charge'     : charge,
                        'invoice_url': charge.get('invoiceUrl', ''),
                        'charge_id'  : charge['id'],
                    })

                if billing_type == 'PIX':
                    pix = get_pix_qrcode(charge['id'])
                    return render(request, 'payments/pix.html', {
                        'order'    : order_ref,
                        'pix'      : pix,
                        'charge_id': charge['id'],
                    })

                if billing_type == 'BOLETO':
                    return render(request, 'payments/boleto.html', {
                        'order' : order_ref,
                        'charge': charge,
                    })

            except Exception as e:
                for order in orders_criados:
                    order.delete()
                erro = str(e)
                if 'CPF é obrigatório' in erro:
                    messages.warning(request, 'Preencha seu CPF no perfil antes de comprar.')
                    return redirect('accounts:profile')
                messages.error(request, f'Erro ao processar pagamento: {erro}')
                return redirect('cart:cart')

    return render(request, 'payments/cart_checkout.html', {
        'items': items,
        'total': total,
        'needs_shipping': needs_shipping,
        'shipping': shipping,
    })


def _build_packages_from_post(request, items, zipcode):
    """Re-cota o frete (server-side) e valida a oferta escolhida por escritor."""
    from apps.delivery.melhor_envios import (
        calcular_frete, shipping_ready_error, MelhorEnviosError,
    )
    groups = _group_cart_by_author(items)
    packages = []
    errors = []

    for author_id, group in groups.items():
        author = group[0].ebook.author
        chosen = request.POST.get(f'offer_{author_id}', '').strip()
        if not chosen:
            errors.append(
                f'Selecione a transportadora para os livros de '
                f'{author.get_full_name() or author.username}.'
            )
            continue

        profile = getattr(author, 'shipping_profile', None)
        ready_error = shipping_ready_error(author)
        if ready_error:
            errors.append(
                f'O escritor {author.get_full_name() or author.username} não está '
                f'pronto para envios físicos: {ready_error}'
            )
            continue

        try:
            offers = calcular_frete(author, profile.zipcode, zipcode, [
                {'ebook': i.ebook, 'quantity': 1, 'unit_value': i.price}
                for i in group
            ])
        except MelhorEnviosError as e:
            errors.append(str(e))
            continue

        offer = next((o for o in offers if o['id'] == chosen), None)
        if not offer:
            errors.append(
                f'O frete escolhido para {author.get_full_name() or author.username} '
                f'expirou. Refaça a cotação.'
            )
            continue

        packages.append({'author': author, 'items': group, 'offer': offer})

    return packages, errors

@login_required
def order_cancel_shipping_view(request, order_id):
    """Comprador cancela um pedido físico antes da postagem (estorno total)."""
    from apps.delivery.views import cancel_shipment

    if request.method != 'POST':
        return redirect('payments:my_orders')

    order = get_object_or_404(Order, order_id=order_id, buyer=request.user)

    if not order.can_cancel_shipping():
        if order.shipping_status == order.SHIPPING_READY:
            messages.error(
                request,
                'O pacote já está com a etiqueta gerada e não pode mais ser '
                'cancelado automaticamente.'
            )
        else:
            messages.error(request, 'Este pedido não pode mais ser cancelado.')
        return redirect('payments:my_orders')

    if not order.shipment:
        messages.error(request, 'Este pedido não possui pacote de envio.')
        return redirect('payments:my_orders')

    result = cancel_shipment(order.shipment)
    if isinstance(result, str):
        messages.error(request, result)
    else:
        messages.success(request, 'Pedido cancelado e valor reembolsado!')

    return redirect('payments:my_orders')


@login_required
def my_orders_view(request):
    """Página com todos os pedidos do usuário — pagos e pendentes."""
    from django.utils import timezone
    from datetime import timedelta

    # Expira pedidos com mais de 24h automaticamente
    expiry_time = timezone.now() - timedelta(hours=24)
    request.user.orders.filter(
        status=Order.STATUS_PENDING,
        created_at__lt=expiry_time
    ).update(status=Order.STATUS_CANCELLED)

    paid_orders    = request.user.orders.filter(
        status=Order.STATUS_PAID
    ).select_related('ebook').order_by('-paid_at')

    pending_orders = request.user.orders.filter(
        status=Order.STATUS_PENDING
    ).select_related('ebook').order_by('-created_at')

    cancelled_orders = request.user.orders.filter(
        status__in=[Order.STATUS_CANCELLED, Order.STATUS_FAILED]
    ).select_related('ebook').order_by('-created_at')[:10]

    return render(request, 'payments/my_orders.html', {
        'paid_orders'     : paid_orders,
        'pending_orders'  : pending_orders,
        'cancelled_orders': cancelled_orders,
    })


def superuser_required(view_func):
    """Decorator — permite acesso apenas a superusuários."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            messages.error(request, 'Acesso restrito ao administrador.')
            return redirect('accounts:login')
        return view_func(request, *args, **kwargs)
    return wrapper


@superuser_required
def admin_withdraws_view(request):
    """Lista todos os pedidos de saque — painel do administrador."""

    status_filter = request.GET.get('status', '')
    search        = request.GET.get('q', '')

    withdraws = WithdrawRequest.objects.select_related('producer').order_by('-created_at')

    if status_filter:
        withdraws = withdraws.filter(status=status_filter)

    if search:
        withdraws = withdraws.filter(
            producer__username__icontains=search
        ) | withdraws.filter(
            producer__first_name__icontains=search
        ) | withdraws.filter(
            producer__email__icontains=search
        )

    # Totais para os cards
    from django.db.models import Sum, Count
    totals = {
        'pending' : WithdrawRequest.objects.filter(status='pending').aggregate(
            count=Count('id'), total=Sum('amount')
        ),
        'approved': WithdrawRequest.objects.filter(status='approved').aggregate(
            count=Count('id'), total=Sum('amount')
        ),
        'paid'    : WithdrawRequest.objects.filter(status='paid').aggregate(
            count=Count('id'), total=Sum('amount')
        ),
    }

    # Paginação
    paginator = Paginator(withdraws, 20)
    page      = request.GET.get('page', 1)
    withdraws = paginator.get_page(page)

    return render(request, 'admin_panel/withdraws.html', {
        'withdraws'    : withdraws,
        'totals'       : totals,
        'status_filter': status_filter,
        'search'       : search,
    })


@superuser_required
def admin_withdraw_detail_view(request, pk):
    """Detalhe de um pedido de saque — upload do comprovante."""
    withdraw = get_object_or_404(WithdrawRequest, pk=pk)
    form     = WithdrawReceiptForm(
        request.POST  or None,
        request.FILES or None,
        instance=withdraw
    )

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            if withdraw.receipt:
                messages.success(
                    request,
                    f'Comprovante enviado! Saque marcado como PAGO automaticamente.'
                )
            else:
                messages.success(request, 'Saque atualizado com sucesso.')
            return redirect('payments:admin_withdraws')

    return render(request, 'admin_panel/withdraw_detail.html', {
        'withdraw': withdraw,
        'form'    : form,
    })

@superuser_required
def admin_commissions_view(request):
    """Relatório de comissões por produtor."""
    from django.db.models import Sum, Count
    from apps.accounts.models import User
    from .models import PlatformConfig

    config     = PlatformConfig.get()
    commission = config.commission_percent / 100
    fixed_fee  = config.fixed_fee or 0

    # Agrupa vendas por produtor
    sales = Order.objects.filter(
        status='paid'
    ).values(
        'ebook__author__id',
        'ebook__author__first_name',
        'ebook__author__last_name',
        'ebook__author__username',
        'ebook__author__email',
    ).annotate(
        total_orders = Count('id'),
        gross        = Sum('amount'),
        freight      = Sum('shipping_cost'),
    ).order_by('-gross')

    # Quem usa a conta própria recebe o frete; conta da Editora → a Editora paga
    from apps.delivery.models import ShippingProfile
    shipping_modes = {
        sp.producer_id: sp.uses_editora_account
        for sp in ShippingProfile.objects.filter(
            producer_id__in=[s['ebook__author__id'] for s in sales]
        )
    }

    # Calcula comissão e líquido por produtor
    producers = []
    total_gross_all      = 0
    total_commission_all = 0
    total_net_all        = 0
    total_freight_all    = 0

    for s in sales:
        gross      = s['gross'] or 0
        orders     = s['total_orders'] or 0
        comm_pct   = gross * commission
        comm_fixed = fixed_fee * orders
        comm       = comm_pct + comm_fixed
        net        = gross - comm
        freight    = s['freight'] or 0
        freight_credit = freight if not shipping_modes.get(
            s['ebook__author__id'], True
        ) else 0

        total_gross_all      += gross
        total_commission_all += comm
        total_net_all        += net
        total_freight_all    += freight

        withdrawn = WithdrawRequest.objects.filter(
            producer_id = s['ebook__author__id'],
            status      = 'paid'
        ).aggregate(t=Sum('amount'))['t'] or 0

        producers.append({
            'id'        : s['ebook__author__id'],
            'name'      : f"{s['ebook__author__first_name']} {s['ebook__author__last_name']}".strip()
                          or s['ebook__author__username'],
            'username'  : s['ebook__author__username'],
            'email'     : s['ebook__author__email'],
            'orders'    : orders,
            'gross'     : gross,
            'commission': comm,
            'net'       : net,
            'freight'   : freight,
            'withdrawn' : withdrawn,
            'available' : net + freight_credit - withdrawn,
        })

    totals = {
        'gross'     : total_gross_all,
        'commission': total_commission_all,
        'net'       : total_net_all,
        'freight'   : total_freight_all,
    }

    return render(request, 'admin_panel/commissions.html', {
        'producers'         : producers,
        'totals'            : totals,
        'commission_percent': config.commission_percent,
        'fixed_fee'         : config.fixed_fee,
    })


@superuser_required
def admin_shipping_view(request):
    """Gestão de Envios: conta da Editora + modo de pagamento por escritor."""
    from apps.delivery.models import EditoraShippingAccount, ShippingProfile

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'toggle_editora':
            profile = ShippingProfile.objects.filter(
                producer_id=request.POST.get('producer_id')
            ).first()
            if profile:
                profile.uses_editora_account = request.POST.get('use_editora') == '1'
                profile.save(update_fields=['uses_editora_account', 'updated_at'])
                messages.success(request, 'Configuração de frete atualizada.')
        return redirect('payments:admin_shipping')

    account  = EditoraShippingAccount.get()
    profiles = ShippingProfile.objects.select_related('producer').order_by(
        'producer__username'
    )

    return render(request, 'admin_panel/shipping.html', {
        'account' : account,
        'profiles': profiles,
    })
