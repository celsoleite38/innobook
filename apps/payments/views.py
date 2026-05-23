from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.conf import settings
from apps.products.models import Ebook
from apps.delivery.utils import create_download_token
from .models import Order, Payment
from .asaas import create_charge, get_charge, get_pix_qrcode
from .emails import send_purchase_confirmation, send_new_sale_notification
import json


# ── Checkout ───────────────────────────────────────────────

@login_required
def checkout_view(request, ebook_id):
    ebook = get_object_or_404(Ebook, id=ebook_id, status='published')

    # Já comprou?
    if request.user.orders.filter(ebook=ebook, status='paid').exists():
        messages.info(request, 'Você já possui este eBook!')
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        billing_type = request.POST.get('billing_type', 'PIX')

        # Cria pedido pendente
        order = Order.objects.create(
            buyer       = request.user,
            ebook       = ebook,
            amount      = ebook.get_price(),
            status      = Order.STATUS_PENDING,
            gateway     = 'asaas',
            buyer_email = request.user.email,
            buyer_name  = request.user.get_full_name() or request.user.username,
        )

        try:
            # Dados do cartão se necessário
            card_data = None
            if billing_type == 'CREDIT_CARD':
                card_data = {
                    'holder_name'   : request.POST.get('holder_name'),
                    'number'        : request.POST.get('card_number', '').replace(' ', ''),
                    'expiry_month'  : request.POST.get('expiry_month'),
                    'expiry_year'   : request.POST.get('expiry_year'),
                    'ccv'           : request.POST.get('ccv'),
                    'cpf'           : request.POST.get('cpf', ''),
                    'postal_code'   : request.POST.get('postal_code', ''),
                    'address_number': request.POST.get('address_number', ''),
                    'phone'         : request.POST.get('phone', ''),
                }

            # Cria cobrança no Asaas
            charge = create_charge(order, billing_type, card_data)

            # Salva ID da cobrança
            order.gateway_order_id = charge['id']
            order.save()

            # Registra pagamento
            Payment.objects.create(
                order        = order,
                method       = billing_type.lower(),
                amount       = order.amount,
                raw_response = charge,
            )

            # Cartão aprovado na hora
            if billing_type == 'CREDIT_CARD' and charge.get('status') == 'CONFIRMED':
                _confirm_order(order, charge['id'])
                return redirect('payments:success', order_id=order.order_id)

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
            # CPF faltando → redireciona para o perfil
            if 'CPF' in erro:
                messages.warning(
                    request,
                    'Por favor, preencha seu CPF no perfil antes de comprar.'
                )
                return redirect('accounts:profile')
            messages.error(request, f'Erro ao processar pagamento: {erro}')
            return redirect('products:detail', slug=ebook.slug)

    return render(request, 'payments/checkout.html', {'ebook': ebook})


# ── Verificar PIX (chamada AJAX da página PIX) ─────────────

@login_required
def check_pix_view(request, charge_id):
    """Verifica se o PIX foi pago (polling do frontend)."""
    try:
        charge = get_charge(charge_id)
        status = charge.get('status', '')

        if status in ('CONFIRMED', 'RECEIVED'):
            order = Order.objects.filter(
                gateway_order_id=charge_id,
                buyer=request.user
            ).first()
            if order and order.status != Order.STATUS_PAID:
                _confirm_order(order, charge_id)
            return JsonResponse({'paid': True, 'order_id': str(order.order_id)})

        return JsonResponse({'paid': False, 'status': status})
    except Exception as e:
        return JsonResponse({'paid': False, 'error': str(e)})


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

@csrf_exempt
def asaas_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event   = data.get('event', '')
    payment = data.get('payment', {})

    if not payment:
        return HttpResponse(status=200)

    charge_id          = payment.get('id')
    external_reference = payment.get('externalReference')

    if not external_reference:
        return HttpResponse(status=200)

    try:
        order = Order.objects.get(order_id=external_reference)
    except Order.DoesNotExist:
        return HttpResponse(status=200)

    # Pagamento confirmado
    if event in ('PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED'):
        if order.status != Order.STATUS_PAID:
            _confirm_order(order, charge_id)

    # Pagamento estornado
    elif event == 'PAYMENT_REFUNDED':
        order.status = Order.STATUS_REFUNDED
        order.save()
        order.download_tokens.update(is_active=False)

    # Pagamento cancelado/vencido
    elif event in ('PAYMENT_DELETED', 'PAYMENT_OVERDUE'):
        order.status = Order.STATUS_CANCELLED
        order.save()

    return HttpResponse(status=200)


# ── Helper interno ─────────────────────────────────────────

def _confirm_order(order, charge_id):
    """Confirma pedido, gera token e envia emails."""
    order.status             = Order.STATUS_PAID
    order.gateway_payment_id = charge_id
    order.paid_at            = timezone.now()
    order.save()

    if not order.download_tokens.exists():
        token = create_download_token(order, days_valid=365, max_downloads=10)
    else:
        token = order.download_tokens.filter(is_active=True).first()

    try:
        send_purchase_confirmation(order, token)
        send_new_sale_notification(order)
    except Exception as e:
        print(f'Erro email: {e}')