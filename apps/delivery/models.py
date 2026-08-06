from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.payments.models import Order
import uuid


class ShippingProfile(models.Model):
    """
    Dados de remetente do escritor + credenciais de conexão
    com o Melhor Envios (OAuth2, por escritor).
    """
    producer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shipping_profile',
        verbose_name='Escritor'
    )

    # Remetente
    full_name = models.CharField(max_length=200, blank=True, verbose_name='Nome remetente')
    document  = models.CharField(max_length=20, blank=True, verbose_name='CPF/CNPJ')
    phone     = models.CharField(max_length=20, blank=True, verbose_name='Telefone')
    zipcode   = models.CharField(max_length=10, blank=True, verbose_name='CEP')
    address   = models.CharField(max_length=255, blank=True, verbose_name='Endereço')
    number    = models.CharField(max_length=20, blank=True, verbose_name='Número')
    complement = models.CharField(max_length=255, blank=True, verbose_name='Complemento')
    district  = models.CharField(max_length=100, blank=True, verbose_name='Bairro')
    city      = models.CharField(max_length=100, blank=True, verbose_name='Cidade')
    state     = models.CharField(max_length=2, blank=True, verbose_name='UF')

    # OAuth Melhor Envios
    me_access_token  = models.TextField(blank=True, verbose_name='Access token ME')
    me_refresh_token = models.TextField(blank=True, verbose_name='Refresh token ME')
    me_expires_at    = models.DateTimeField(null=True, blank=True, verbose_name='Token expira em')

    # Pagamento do frete: True = conta da Editora (padrão) | False = conta própria
    uses_editora_account = models.BooleanField(
        default=True,
        verbose_name='Usar conta da Editora no Melhor Envios'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Perfil de Envio'
        verbose_name_plural = 'Perfis de Envio'

    @property
    def is_connected(self):
        return bool(self.me_access_token and self.me_refresh_token)

    @property
    def has_origin_address(self):
        return all([self.full_name, self.zipcode, self.address,
                    self.number, self.district, self.city, self.state])

    def __str__(self):
        return f'Envio de {self.producer.username}'


class EditoraShippingAccount(models.Model):
    """
    Conta Melhor Envios da Editora (singleton).

    Usada como pagadora do frete para escritores com
    ShippingProfile.uses_editora_account = True (padrão).
    """
    holder_name     = models.CharField(max_length=200, blank=True, verbose_name='Titular da conta')
    me_access_token  = models.TextField(blank=True, verbose_name='Access token ME')
    me_refresh_token = models.TextField(blank=True, verbose_name='Refresh token ME')
    me_expires_at    = models.DateTimeField(null=True, blank=True, verbose_name='Token expira em')
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Conta Melhor Envios da Editora'
        verbose_name_plural = 'Contas Melhor Envios da Editora'

    def __str__(self):
        return f'Conta ME da Editora — {self.holder_name or "não conectada"}'

    @property
    def is_connected(self):
        return bool(self.me_access_token and self.me_refresh_token)

    @classmethod
    def get(cls):
        """Retorna o singleton, criando-o se necessário."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Shipment(models.Model):
    """
    Pacote físico (grupo de pedidos de um escritor) enviado via Melhor Envios.
    """
    STATUS_AWAITING  = 'awaiting'
    STATUS_READY     = 'ready'
    STATUS_SHIPPED   = 'shipped'
    STATUS_DELIVERED = 'delivered'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_AWAITING,  'Aguardando envio'),
        (STATUS_READY,     'Aguardando postagem'),
        (STATUS_SHIPPED,   'Enviado'),
        (STATUS_DELIVERED, 'Entregue'),
        (STATUS_CANCELLED, 'Cancelado'),
    ]

    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shipments',
        verbose_name='Escritor'
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='purchased_shipments',
        null=True, blank=True,
        verbose_name='Comprador'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AWAITING,
        verbose_name='Status'
    )

    # Frete (escolhido na cotação)
    freight_cost = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        verbose_name='Frete (R$)'
    )
    offer_id = models.CharField(
        max_length=200, blank=True,
        verbose_name='ID da oferta no ME'
    )
    carrier = models.CharField(max_length=100, blank=True, verbose_name='Transportadora')
    delivery_time = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Prazo (dias úteis)'
    )
    quote_payload = models.JSONField(
        default=dict, blank=True,
        verbose_name='Payload da cotação'
    )

    # Melhor Envios
    melhor_envios_id = models.CharField(
        max_length=200, blank=True,
        verbose_name='ID do envio no ME'
    )
    tracking_code = models.CharField(
        max_length=50, blank=True,
        verbose_name='Código de rastreio'
    )
    tracking_url = models.URLField(
        blank=True,
        verbose_name='URL de rastreio'
    )
    label_pdf = models.FileField(
        upload_to='labels/',
        blank=True, null=True,
        verbose_name='Etiqueta (PDF)'
    )
    print_url = models.URLField(
        blank=True,
        verbose_name='URL de impressão da etiqueta'
    )

    # Datas
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    posted_at   = models.DateTimeField(null=True, blank=True, verbose_name='Postado em')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='Entregue em')

    class Meta:
        verbose_name        = 'Pacote de Envio'
        verbose_name_plural = 'Pacotes de Envio'
        ordering            = ['-created_at']

    def get_destination_address(self):
        order = self.orders.filter(
            shipping_name__gt=''
        ).exclude(shipping_zipcode='').first() or self.orders.first()
        if not order:
            return None
        return {
            'name': order.shipping_name,
            'zipcode': order.shipping_zipcode,
            'address': order.shipping_address,
            'number': order.shipping_number,
            'complement': order.shipping_complement,
            'district': order.shipping_district,
            'city': order.shipping_city,
            'state': order.shipping_state,
        }

    def sync_order_status(self):
        """Sincroniza shipping_status/rastreio nos pedidos do pacote."""
        self.orders.update(
            shipping_status=self.status,
            tracking_code=self.tracking_code,
            shipped_at=self.posted_at,
            delivered_at=self.delivered_at,
        )

    def __str__(self):
        return f'Pacote #{self.pk} — {self.carrier or "sem transportadora"} — {self.get_status_display()}'


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