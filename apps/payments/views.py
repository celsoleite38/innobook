from urllib import request

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.conf import settings
from apps.products.models import Ebook
from apps.delivery.utils import create_download_token
from .models import Order, Payment, WithdrawRequest
from .asaas import create_charge, get_charge, get_pix_qrcode
from .emails import send_purchase_confirmation, send_new_sale_notification
import json

from django.contrib.admin.views.decorators import staff_member_required
from functools import wraps
from django.core.paginator import Paginator
from .forms import WithdrawReceiptForm



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
            if 'CPF é obrigatório' in erro:
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
    # 1. Valida token do Asaas - 401 não pausa fila
    #asaas_token = request.headers.get('asaas-access-token')
    #if asaas_token != getattr(settings, 'ASAAS_WEBHOOK_TOKEN', None):
    #    logger.warning(f"Webhook com token inválido: {asaas_token}")
    #    return HttpResponse(status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Webhook Asaas com JSON inválido")
        return HttpResponse(status=400) # 400 também não pausa

    event = data.get('event', '')
    payment = data.get('payment', {})

    if not payment:
        return JsonResponse({"status": "ignored"}, status=200)

    charge_id = payment.get('id')
    external_reference = payment.get('externalReference')

    if not external_reference:
        logger.info(f"Webhook sem externalReference: {charge_id}")
        return JsonResponse({"status": "ignored"}, status=200)

    try:
        order = Order.objects.get(order_id=external_reference)
    except Order.DoesNotExist:
        logger.error(f"Pedido não encontrado no webhook: {external_reference}")
        return JsonResponse({"status": "order_not_found"}, status=200)

    # 2. Idempotência - se já tá pago, só retorna 200
    if order.status == Order.STATUS_PAID:
        logger.info(f"Pedido {order.order_id} já pago. Ignorando webhook duplicado.")
        return JsonResponse({"status": "already_paid"}, status=200)

    # 3. Processa eventos
    if event in ('PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED'):
        _confirm_order(order, charge_id)
        logger.info(f"Pedido {order.order_id} confirmado via webhook")

    elif event == 'PAYMENT_REFUNDED':
        order.status = Order.STATUS_REFUNDED
        order.save()
        order.download_tokens.update(is_active=False)
        logger.info(f"Pedido {order.order_id} estornado")

    elif event in ('PAYMENT_DELETED', 'PAYMENT_OVERDUE'):
        order.status = Order.STATUS_CANCELLED
        order.save()
        logger.info(f"Pedido {order.order_id} cancelado/vencido")

    # 4. Sempre retorna 200 pro Asaas não pausar
    return JsonResponse({"status": "received"}, status=200)


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

@login_required
def cart_checkout_view(request):
    from apps.cart.models import Cart, CartItem

    try:
        cart = request.user.cart
    except Exception:
        messages.error(request, 'Carrinho vazio.')
        return redirect('cart:cart')

    items = cart.items.select_related('ebook').all()

    if not items:
        messages.error(request, 'Seu carrinho está vazio.')
        return redirect('cart:cart')

    # Remove itens já comprados
    paid_ids = request.user.orders.filter(
        status='paid'
    ).values_list('ebook_id', flat=True)
    items = items.exclude(ebook_id__in=paid_ids)

    if not items:
        messages.info(request, 'Todos os eBooks já foram comprados!')
        return redirect('accounts:dashboard')

    total = sum(item.price for item in items)

    if request.method == 'POST':
        billing_type = request.POST.get('billing_type', 'PIX')
        orders_criados = []

        try:
            for item in items:
                order = Order.objects.create(
                    buyer       = request.user,
                    ebook       = item.ebook,
                    amount      = item.price,
                    status      = Order.STATUS_PENDING,
                    gateway     = 'asaas',
                    buyer_email = request.user.email,
                    buyer_name  = request.user.get_full_name() or request.user.username,
                )
                orders_criados.append(order)

            # Cria UMA cobrança no Asaas com o total
            # Usamos o primeiro order como referência
            order_ref = orders_criados[0]
            order_ref.amount = total
            order_ref.save()

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
                }

            charge = create_charge(order_ref, billing_type, card_data)
            order_ref.gateway_order_id = charge['id']
            order_ref.save()

            # Salva charge_id nos outros pedidos também
            for order in orders_criados[1:]:
                order.gateway_order_id = charge['id']
                order.save()

            Payment.objects.create(
                order        = order_ref,
                method       = billing_type.lower(),
                amount       = total,
                raw_response = charge,
            )

            # Limpa o carrinho
            cart.items.all().delete()

            if billing_type == 'CREDIT_CARD' and charge.get('status') == 'CONFIRMED':
                for order in orders_criados:
                    _confirm_order(order, charge['id'])
                return redirect('payments:success', order_id=order_ref.order_id)

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
    })

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
    ).order_by('-gross')

    # Calcula comissão e líquido por produtor
    producers = []
    total_gross_all      = 0
    total_commission_all = 0
    total_net_all        = 0

    for s in sales:
        gross      = s['gross'] or 0
        comm       = gross * commission
        net        = gross - comm

        total_gross_all      += gross
        total_commission_all += comm
        total_net_all        += net

        # Saques já realizados pelo produtor
        withdrawn = WithdrawRequest.objects.filter(
            producer_id = s['ebook__author__id'],
            status__in  = ['approved', 'paid']
        ).aggregate(t=Sum('amount'))['t'] or 0

        producers.append({
            'id'        : s['ebook__author__id'],
            'name'      : f"{s['ebook__author__first_name']} {s['ebook__author__last_name']}".strip()
                          or s['ebook__author__username'],
            'username'  : s['ebook__author__username'],
            'email'     : s['ebook__author__email'],
            'orders'    : s['total_orders'],
            'gross'     : gross,
            'commission': comm,
            'net'       : net,
            'withdrawn' : withdrawn,
            'available' : net - withdrawn,
        })

    totals = {
        'gross'     : total_gross_all,
        'commission': total_commission_all,
        'net'       : total_net_all,
    }

    return render(request, 'admin_panel/commissions.html', {
        'producers'         : producers,
        'totals'            : totals,
        'commission_percent': config.commission_percent,
    })
