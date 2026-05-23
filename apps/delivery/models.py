from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.payments.models import Order
import uuid


class DownloadToken(models.Model):
    """
    Token único gerado após pagamento confirmado.
    Controla acesso ao PDF sem expor a URL real do arquivo.
    """

    order       = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='download_tokens',
        verbose_name='Pedido'
    )

    # Token único e imprevisível
    token       = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name='Token'
    )

    # Controle de uso
    downloads       = models.PositiveIntegerField(
        default=0,
        verbose_name='Downloads realizados'
    )
    max_downloads   = models.PositiveIntegerField(
        default=5,
        verbose_name='Máximo de downloads'
    )

    # Controle de expiração
    expires_at      = models.DateTimeField(verbose_name='Expira em')
    is_active       = models.BooleanField(default=True, verbose_name='Ativo')

    # Rastreamento
    last_download_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Último download'
    )
    last_ip         = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name='Último IP'
    )

    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Token de Download'
        verbose_name_plural = 'Tokens de Download'
        ordering = ['-created_at']

    # ------------------------------------------------------------------ #
    #  Propriedades e métodos                                             #
    # ------------------------------------------------------------------ #

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_limit_reached(self):
        return self.downloads >= self.max_downloads

    @property
    def is_valid(self):
        """Token válido = ativo + não expirado + dentro do limite."""
        return self.is_active and not self.is_expired and not self.is_limit_reached

    @property
    def remaining_downloads(self):
        return max(0, self.max_downloads - self.downloads)

    def register_download(self, ip=None):
        """Registra um download e atualiza os contadores."""
        self.downloads += 1
        self.last_download_at = timezone.now()
        if ip:
            self.last_ip = ip
        # Desativa automaticamente se atingiu o limite
        if self.is_limit_reached:
            self.is_active = False
        self.save()

    def __str__(self):
        return f'Token {self.token} — {self.order.ebook.title}'


class DownloadLog(models.Model):
    """
    Log detalhado de cada download realizado.
    Útil para auditoria e suporte.
    """

    token       = models.ForeignKey(
        DownloadToken,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name='Token'
    )
    ip_address  = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name='IP'
    )
    user_agent  = models.TextField(
        blank=True,
        verbose_name='User Agent'
    )
    downloaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Data do download'
    )

    class Meta:
        verbose_name = 'Log de Download'
        verbose_name_plural = 'Logs de Downloads'
        ordering = ['-downloaded_at']

    def __str__(self):
        return f'Download {self.token.order.ebook.title} — {self.downloaded_at}'