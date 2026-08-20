from django.shortcuts import get_object_or_404, render, redirect
from django.http import FileResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from apps.payments.models import Order
from .models import DownloadToken, DownloadLog, Shipment, ShippingProfile
from .utils import get_client_ip
from .forms import ShippingProfileForm
import os


# ── Painel do escritor: envios ──────────────────────────────

def _get_remetente_or_create(user):
    profile, _ = ShippingProfile.objects.get_or_create(producer=user)
    return profile


@login_required
def shipping_panel_view(request):
    from apps.accounts.views import producer_required

    return producer_required(_shipping_panel)(request)


def _shipping_panel(request):
    profile = _get_remetente_or_create(request.user)

    # Obrigatório: sem endereço de remetente não há frete/cotação
    if not profile.has_origin_address:
        messages.info(
            request,
            'Antes de gerenciar seus envios, preencha o endereço de remetente '
            '(obrigatório para calcular e emitir o frete).'
        )
        return redirect('delivery:shipping_profile')

    form = ShippingProfileForm(instance=profile)

    shipments = Shipment.objects.filter(
        producer=request.user
    ).prefetch_related('orders', 'orders__ebook')

    return render(request, 'delivery/shipping_panel.html', {
        'profile': profile,
        'form': form,
        'shipments': shipments,
    })


@login_required
def shipping_profile_view(request):
    from apps.accounts.views import producer_required

    return producer_required(_shipping_profile)(request)


def _shipping_profile(request):
    profile = _get_remetente_or_create(request.user)
    form = ShippingProfileForm(
        request.POST or None,
        instance=profile,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Endereço de remetente atualizado!')
        return redirect('delivery:shipping_panel')
    return render(request, 'delivery/shipping_profile.html', {
        'form': form,
        'profile': profile,
    })


@login_required
def oauth_start(request):
    from apps.accounts.views import producer_required

    return producer_required(_oauth_start)(request)


def _oauth_start(request):
    from .melhor_envios import get_authorize_url
    url = get_authorize_url(request.user)
    return redirect(url)


@login_required
def oauth_callback(request):
    from .melhor_envios import exchange_code, editora_exchange_code, MelhorEnviosError

    error = request.GET.get('error')
    if error:
        messages.error(request, f'Autorização negada no Melhor Envios: {error}')
        return redirect('delivery:shipping_panel')

    code = request.GET.get('code')
    if not code:
        messages.error(request, 'Resposta do Melhor Envios inválida.')
        return redirect('delivery:shipping_panel')

    # Fluxo da conta da Editora (state='editora', restrito a superusuário)
    state = request.GET.get('state')
    if state == 'editora':
        if not request.user.is_superuser:
            messages.error(request, 'Acesso restrito ao administrador.')
            return redirect('accounts:login')
        try:
            editora_exchange_code(code)
            messages.success(request, 'Conta da Editora conectada ao Melhor Envios!')
        except MelhorEnviosError as e:
            messages.error(request, f'Erro ao conectar: {e}')
        except Exception as e:
            messages.error(request, f'Erro ao conectar: {e}')
        return redirect('payments:admin_shipping')

    # Confere que o code pertence ao usuário logado (state = producer.id)
    if state and str(request.user.id) != str(state):
        messages.error(request, 'Resposta de autorização não pertence à sua conta.')
        return redirect('delivery:shipping_panel')

    try:
        exchange_code(request.user, code)
        messages.success(request, 'Conta conectada ao Melhor Envios!')
    except MelhorEnviosError as e:
        messages.error(request, f'Erro ao conectar: {e}')
    except Exception as e:
        messages.error(request, f'Erro ao conectar: {e}')

    return redirect('delivery:shipping_panel')


@login_required
def editora_oauth_start(request):
    """Inicia o OAuth da conta da Editora (apenas superusuário)."""
    from .melhor_envios import editora_get_authorize_url

    if not request.user.is_superuser:
        messages.error(request, 'Acesso restrito ao administrador.')
        return redirect('accounts:login')
    return redirect(editora_get_authorize_url())


@login_required
def shipping_generate_label(request, pk):
    from apps.accounts.views import producer_required

    return producer_required(_shipping_generate_label)(request, pk)


def _shipping_generate_label(request, pk):
    from .melhor_envios import gerar_etiqueta_completa, MelhorEnviosError

    shipment = get_object_or_404(
        Shipment, pk=pk, producer=request.user
    )

    if not shipment.orders.filter(status='paid').exists():
        messages.error(request, 'Este pacote ainda não tem pagamento confirmado.')
        return redirect('delivery:shipping_panel')

    if shipment.status != Shipment.STATUS_AWAITING:
        messages.warning(request, 'Este pacote já foi processado.')
        return redirect('delivery:shipping_panel')

    try:
        gerar_etiqueta_completa(shipment)
        messages.success(
            request,
            'Etiqueta gerada! Abra o link de impressão e poste o pacote.'
        )
    except MelhorEnviosError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Erro ao gerar etiqueta: {e}')

    return redirect('delivery:shipping_panel')


@login_required
def shipping_mark_shipped(request, pk):
    from apps.accounts.views import producer_required

    return producer_required(_shipping_mark_shipped)(request, pk)


def _shipping_mark_shipped(request, pk):
    shipment = get_object_or_404(
        Shipment, pk=pk, producer=request.user
    )
    if shipment.status not in (Shipment.STATUS_AWAITING, Shipment.STATUS_READY):
        messages.warning(request, 'Este pacote não está aguardando envio.')
        return redirect('delivery:shipping_panel')

    shipment.status = Shipment.STATUS_SHIPPED
    shipment.posted_at = timezone.now()
    shipment.save(update_fields=['status', 'posted_at', 'updated_at'])
    shipment.sync_order_status()

    try:
        from apps.payments.emails import send_shipped_notification
        send_shipped_notification(shipment)
    except Exception as e:
        print(f'Erro email envio: {e}')

    messages.success(request, 'Pacote marcado como enviado!')
    return redirect('delivery:shipping_panel')


@login_required
def shipping_cancel(request, pk):
    """Cancelamento pelo escritor — antes da postagem."""
    from apps.accounts.views import producer_required

    return producer_required(_shipping_cancel)(request, pk)


def _shipping_cancel(request, pk):
    shipment = get_object_or_404(
        Shipment, pk=pk, producer=request.user
    )
    result = cancel_shipment(shipment)
    if isinstance(result, str):
        messages.error(request, result)
    else:
        messages.success(request, 'Pacote cancelado e valor reembolsado ao comprador.')
    return redirect('delivery:shipping_panel')


# ── Cancelamento (compartilhado: escritor e comprador) ──────

def cancel_shipment(shipment):
    """
    Cancela o pacote (total): consulta status real no ME, cancela a etiqueta,
    estorna o pagamento (produto + frete) e devolve o estoque.
    Retorna True em sucesso ou a mensagem de erro.
    """
    from apps.delivery.melhor_envios import (
        cancelar_etiqueta, consultar_status, MelhorEnviosError,
    )

    paid_orders = list(shipment.orders.filter(status='paid'))

    if not paid_orders:
        return 'Este pacote não possui pedidos pagos para cancelar.'

    # Trava o pacote para evitar corrida com a postagem
    locked = Shipment.objects.select_for_update().filter(pk=shipment.pk).first()
    if not locked:
        return 'Pacote não encontrado.'

    if locked.status not in (Shipment.STATUS_AWAITING, Shipment.STATUS_READY):
        return 'Este pacote já foi postado e não pode ser cancelado.'

    # Consulta o status real no Melhor Envios (não confia só no nosso status)
    if locked.melhor_envios_id:
        try:
            status_data = consultar_status(locked)
            me_status = (status_data or {}).get('status', '')
            if me_status in ('posting', 'posted', 'delivered', 'released', 'generated'):
                # Ainda pode cancelar se não foi postado de fato
                if me_status in ('posted', 'delivered', 'released'):
                    return 'O pacote já foi postado e não pode ser cancelado.'
        except MelhorEnviosError as e:
            return f'Erro ao verificar o status no Melhor Envios: {e}'

    try:
        if locked.melhor_envios_id:
            cancelar_etiqueta(locked)
        else:
            locked.status = Shipment.STATUS_CANCELLED
            locked.save(update_fields=['status', 'updated_at'])
            locked.sync_order_status()
    except MelhorEnviosError as e:
        return f'Erro ao cancelar a etiqueta: {e}'

    # Estorno no Asaas
    charge_ids = set(o.gateway_order_id for o in paid_orders if o.gateway_order_id)
    for charge_id in charge_ids:
        try:
            from apps.payments.asaas import refund_charge
            refund_charge(charge_id)
        except Exception as e:
            return f'Pagamento não pôde ser estornado automaticamente: {e}'

    # Atualiza pedidos + estoque
    for order in paid_orders:
        order.status = Order.STATUS_REFUNDED
        order.shipping_status = Shipment.STATUS_CANCELLED
        order.cancel_requested_at = timezone.now()
        order.save(update_fields=[
            'status', 'shipping_status', 'cancel_requested_at', 'updated_at'
        ])
        ebook = order.ebook
        ebook.physical_stock += 1
        ebook.save(update_fields=['physical_stock'])
        order.download_tokens.update(is_active=False)

    try:
        from apps.payments.emails import send_cancelled_notification
        send_cancelled_notification(shipment)
    except Exception as e:
        print(f'Erro email cancelamento: {e}')

    return True


# ── Webhook Melhor Envios ───────────────────────────────────

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def melhor_envios_webhook(request):
    """Atualiza o status dos pacotes conforme eventos do Melhor Envios."""
    from .melhor_envios import verify_webhook_signature, map_webhook_event

    signature = request.headers.get('X-ME-Signature', '')
    body = request.body

    if not verify_webhook_signature(body, signature):
        logger.warning(f'Webhook ME com assinatura inválida.')
        return HttpResponse(status=401)

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event = data.get('event', '')
    payload = data.get('data', {})
    me_id = str(payload.get('id', ''))

    internal_status = map_webhook_event(event)
    if not internal_status:
        logger.info(f'Evento ME ignorado: {event}')
        return JsonResponse({'status': 'ignored'}, status=200)

    if not me_id:
        return JsonResponse({'status': 'no_id'}, status=200)

    shipment = Shipment.objects.filter(melhor_envios_id=me_id).first()
    if not shipment:
        logger.error(f'Pacote não encontrado para etiqueta ME: {me_id}')
        return JsonResponse({'status': 'not_found'}, status=200)

    # Idempotência
    if shipment.status == internal_status:
        return JsonResponse({'status': 'already'}, status=200)

    shipment.status = internal_status

    tracking = payload.get('tracking') or payload.get('self_tracking') or ''
    if tracking:
        shipment.tracking_code = tracking
    if payload.get('tracking_url'):
        shipment.tracking_url = payload['tracking_url']

    if internal_status == Shipment.STATUS_SHIPPED and not shipment.posted_at:
        shipment.posted_at = payload.get('posted_at') or timezone.now()
    elif internal_status == Shipment.STATUS_DELIVERED:
        shipment.delivered_at = payload.get('delivered_at') or timezone.now()
    elif internal_status == Shipment.STATUS_CANCELLED:
        shipment.delivered_at = None

    shipment.save(update_fields=[
        'status', 'tracking_code', 'tracking_url',
        'posted_at', 'delivered_at', 'updated_at',
    ])
    shipment.sync_order_status()

    try:
        if internal_status == Shipment.STATUS_SHIPPED:
            from apps.payments.emails import send_shipped_notification
            send_shipped_notification(shipment)
        elif internal_status == Shipment.STATUS_DELIVERED:
            from apps.payments.emails import send_delivered_notification
            send_delivered_notification(shipment)
    except Exception as e:
        logger.error(f'Erro email webhook: {e}')

    logger.info(f'Pacote {shipment.pk} -> {internal_status}')
    return JsonResponse({'status': 'ok'}, status=200)


@login_required
def download_ebook(request, token):
    dt = get_object_or_404(DownloadToken, token=token)

    if dt.order.buyer != request.user:
        return HttpResponseForbidden('Acesso negado.')

    if not dt.is_valid:
        if dt.is_expired:
            return HttpResponseForbidden('Link expirado.')
        if dt.is_limit_reached:
            return HttpResponseForbidden('Limite de downloads atingido.')
        return HttpResponseForbidden('Token inválido.')

    # Formato solicitado (pdf, epub, mobi) — padrão PDF
    fmt = request.GET.get('format', 'pdf').lower()

    ebook = dt.order.ebook

    if fmt == 'epub' and ebook.file_epub:
        file_path    = ebook.file_epub.path
        content_type = 'application/epub+zip'
        extension    = 'epub'
    elif fmt == 'mobi' and ebook.file_mobi:
        file_path    = ebook.file_mobi.path
        content_type = 'application/x-mobipocket-ebook'
        extension    = 'mobi'
    elif ebook.file:
        file_path    = ebook.file.path
        content_type = 'application/pdf'
        extension    = 'pdf'
    else:
        return HttpResponseForbidden('Arquivo digital não disponível para este eBook.')

    if not os.path.exists(file_path):
        return HttpResponseForbidden('Arquivo não encontrado.')

    ip = get_client_ip(request)
    dt.register_download(ip=ip)

    DownloadLog.objects.create(
        token      = dt,
        ip_address = ip,
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500],
    )

    filename = f"{ebook.title}.{extension}"
    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_bonus(request, token, bonus_id):
    """Download de eBook bônus vinculado a um pedido pago."""
    from apps.products.models import EbookBonus

    dt = get_object_or_404(DownloadToken, token=token)

    if dt.order.buyer != request.user:
        return HttpResponseForbidden('Acesso negado.')

    if not dt.is_valid:
        return HttpResponseForbidden('Token inválido ou expirado.')

    bonus = get_object_or_404(EbookBonus, pk=bonus_id, ebook=dt.order.ebook)

    fmt = request.GET.get('format', 'pdf').lower()

    if fmt == 'epub' and bonus.file_epub:
        file_path    = bonus.file_epub.path
        content_type = 'application/epub+zip'
        extension    = 'epub'
    elif fmt == 'mobi' and bonus.file_mobi:
        file_path    = bonus.file_mobi.path
        content_type = 'application/x-mobipocket-ebook'
        extension    = 'mobi'
    elif bonus.file:
        file_path    = bonus.file.path
        content_type = 'application/pdf'
        extension    = 'pdf'
    else:
        return HttpResponseForbidden('Arquivo não disponível.')

    if not os.path.exists(file_path):
        return HttpResponseForbidden('Arquivo não encontrado.')

    filename = f"{bonus.title}.{extension}"
    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response