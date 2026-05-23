from django.utils import timezone
from datetime import timedelta
from .models import DownloadToken


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