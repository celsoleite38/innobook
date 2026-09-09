from django.utils import timezone
from datetime import timedelta
from .models import DownloadToken


def get_or_create_download_token(order, days_valid=365, max_downloads=10):
    """
    Devolve um token de download válido para o pedido.

    Se já existir um token válido (ativo, não expirado e dentro do limite),
    retorna-o. Caso contrário, renova/cria um novo token.

    Renovação automática (política "renovar sempre"): leitor com pedido
    pago de eBook digital/combo sempre consegue baixar, mesmo se o token
    anterior expirou ou atingiu o limite de downloads.

    Só cria token para pedidos pagos de versão digital ou combo
    (livro físico puro não gera download).
    """
    from apps.payments.models import Order
    from apps.products.models import FORMAT_DIGITAL, FORMAT_COMBO

    if order.status != Order.STATUS_PAID:
        return None

    if order.variant not in (FORMAT_DIGITAL, FORMAT_COMBO):
        return None

    valid = order.download_tokens.filter(
        is_active=True,
        expires_at__gt=timezone.now(),
        downloads__lt=max_downloads,
    ).first()
    if valid:
        return valid

    # Renova: reutiliza o token existente se ainda estiver ativo,
    # senão cria um novo — garante um único link por pedido.
    token = order.download_tokens.filter(is_active=True).first()
    if token:
        token.downloads = 0
        token.expires_at = timezone.now() + timedelta(days=days_valid)
        token.save(update_fields=['downloads', 'expires_at'])
        return token

    token = create_download_token(
        order, days_valid=days_valid, max_downloads=max_downloads
    )
    return token


def create_download_token(order, days_valid=30, max_downloads=5):
    """
    Cria um token de download para um pedido pago.
    Chamado automaticamente após confirmação do pagamento.
    """
    token = DownloadToken.objects.create(
        order         = order,
        max_downloads = max_downloads,
        expires_at    = timezone.now() + timedelta(days=days_valid),
    )
    return token


def get_client_ip(request):
    """Extrai o IP real do cliente mesmo atrás de proxy."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')