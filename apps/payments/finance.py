from django.db.models import Sum, Count
from decimal import Decimal
from .models import Order, WithdrawRequest, PlatformConfig


def get_producer_financial(producer):
    """
    Retorna resumo financeiro completo do produtor.
    """
    config = PlatformConfig.get()
    commission = config.commission_percent / 100

    # Total de vendas pagas
    paid_orders = Order.objects.filter(
        ebook__author=producer,
        status='paid'
    )

    total_gross  = paid_orders.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    total_orders = paid_orders.count()

    # Comissão e líquido
    total_commission = total_gross * Decimal(str(commission))
    total_net        = total_gross - total_commission

    # Total já sacado (aprovado ou pago)
    total_withdrawn = WithdrawRequest.objects.filter(
        producer=producer,
        status__in=['approved', 'paid']
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Saques pendentes
    total_pending_withdraw = WithdrawRequest.objects.filter(
        producer=producer,
        status='pending'
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Saldo disponível para saque
    available = total_net - total_withdrawn - total_pending_withdraw

    return {
        'total_gross'           : total_gross,
        'total_orders'          : total_orders,
        'commission_percent'    : config.commission_percent,
        'total_commission'      : total_commission,
        'total_net'             : total_net,
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
        net        = gross * (1 - commission)
        s['net']   = net
        result.append(s)

    return result