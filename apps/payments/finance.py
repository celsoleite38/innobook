from django.db.models import Sum, Count
from decimal import Decimal
from .models import Order, WithdrawRequest, PlatformConfig


def get_producer_financial(producer):
    """
    Retorna resumo financeiro completo do produtor.
    """
    config = PlatformConfig.get()
    commission = config.commission_percent / 100
    fixed_fee  = config.fixed_fee or Decimal('0')

    # Total de vendas pagas
    paid_orders = Order.objects.filter(
        ebook__author=producer,
        status='paid'
    )

    total_gross  = paid_orders.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    total_orders = paid_orders.count()

    # Comissão percentual
    total_commission_pct = total_gross * Decimal(str(commission))
    # Taxa fixa total
    total_fixed_fee     = fixed_fee * Decimal(str(total_orders))
    # Comissão total = percentual + fixa
    total_commission    = total_commission_pct + total_fixed_fee
    total_net           = total_gross - total_commission

    # Fretes pagos (livros físicos)
    try:
        profile = producer.shipping_profile
    except Exception:
        profile = None
    if profile and not profile.uses_editora_account:
        total_shipping = paid_orders.aggregate(
            t=Sum('shipping_cost')
        )['t'] or Decimal('0')
    else:
        total_shipping = Decimal('0')

    # Total já sacado (somente PAGO — com comprovante enviado)
    total_withdrawn = WithdrawRequest.objects.filter(
        producer=producer,
        status='paid'
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Saques pendentes
    total_pending_withdraw = WithdrawRequest.objects.filter(
        producer=producer,
        status='pending'
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Saldo disponível para saque
    available = total_net + total_shipping - total_withdrawn - total_pending_withdraw

    return {
        'total_gross'           : total_gross,
        'total_orders'          : total_orders,
        'commission_percent'    : config.commission_percent,
        'fixed_fee'             : fixed_fee,
        'total_commission'      : total_commission,
        'total_net'             : total_net,
        'total_shipping'        : total_shipping,
        'total_withdrawn'       : total_withdrawn,
        'total_pending_withdraw': total_pending_withdraw,
        'available'             : max(available, Decimal('0')),
        'min_withdraw'          : config.min_withdraw,
        'can_withdraw'          : available >= config.min_withdraw,
        'withdraw_info'         : config.withdraw_info,
    }


def get_producer_sales_by_ebook(producer):
    """Vendas agrupadas por eBook."""
    config     = PlatformConfig.get()
    commission = config.commission_percent / 100
    fixed_fee  = config.fixed_fee or Decimal('0')

    sales = Order.objects.filter(
        ebook__author=producer,
        status='paid'
    ).values(
        'ebook__id',
        'ebook__title',
        'ebook__cover',
    ).annotate(
        total_orders = Count('id'),
        gross        = Sum('amount'),
    ).order_by('-total_orders')

    result = []
    for s in sales:
        gross      = s['gross'] or Decimal('0')
        orders     = s['total_orders'] or 0
        commission_total = gross * Decimal(str(commission)) + fixed_fee * Decimal(str(orders))
        net        = gross - commission_total
        s['net']   = net
        result.append(s)

    return result