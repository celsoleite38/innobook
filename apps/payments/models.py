from django.db import models
from django.conf import settings
from apps.products.models import Ebook
import uuid


class Order(models.Model):

    STATUS_PENDING   = 'pending'
    STATUS_PAID      = 'paid'
    STATUS_FAILED    = 'failed'
    STATUS_REFUNDED  = 'refunded'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING,   'Aguardando Pagamento'),
        (STATUS_PAID,      'Pago'),
        (STATUS_FAILED,    'Falhou'),
        (STATUS_REFUNDED,  'Reembolsado'),
        (STATUS_CANCELLED, 'Cancelado'),
    ]

    # Identificador único do pedido (visível para o cliente)
    order_id    = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Relacionamentos
    buyer       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders',
        verbose_name='Comprador'
    )
    ebook       = models.ForeignKey(
        Ebook,
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name='eBook'
    )

    # Valores (salvamos o preço no momento da compra!)
    amount      = models.DecimalField(
        max_digits=8, decimal_places=2,
        verbose_name='Valor pago'
    )
    platform_fee = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=0,
        verbose_name='Taxa da plataforma'
    )
    producer_amount = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=0,
        verbose_name='Valor para o produtor'
    )

    # Gateway de pagamento
    gateway         = models.CharField(
        max_length=50, blank=True,
        verbose_name='Gateway'
    )
    gateway_order_id = models.CharField(
        max_length=200, blank=True,
        verbose_name='ID no gateway'
    )
    gateway_payment_id = models.CharField(
        max_length=200, blank=True,
        verbose_name='ID do pagamento'
    )

    # Status
    status      = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name='Status'
    )

    # Dados do comprador no momento da compra
    buyer_email = models.EmailField(verbose_name='Email do comprador')
    buyer_name  = models.CharField(max_length=200, verbose_name='Nome do comprador')

    # Datas
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    paid_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Calcula automaticamente taxa e valor do produtor (10% plataforma)
        if self.amount and not self.platform_fee:
            self.platform_fee   = self.amount * 10 / 100
            self.producer_amount = self.amount - self.platform_fee
        super().save(*args, **kwargs)

    def is_paid(self):
        return self.status == self.STATUS_PAID

    def __str__(self):
        return f'Pedido #{self.order_id} — {self.buyer_name} — {self.get_status_display()}'


class Payment(models.Model):
    """
    Histórico de tentativas de pagamento de um pedido.
    Um Order pode ter várias tentativas de Payment.
    """

    METHOD_PIX          = 'pix'
    METHOD_CREDIT_CARD  = 'credit_card'
    METHOD_BOLETO       = 'boleto'

    METHOD_CHOICES = [
        (METHOD_PIX,         'PIX'),
        (METHOD_CREDIT_CARD, 'Cartão de Crédito'),
        (METHOD_BOLETO,      'Boleto'),
    ]

    order       = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name='Pedido'
    )
    method      = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        verbose_name='Método'
    )
    amount      = models.DecimalField(
        max_digits=8, decimal_places=2,
        verbose_name='Valor'
    )
    raw_response = models.JSONField(
        default=dict, blank=True,
        verbose_name='Resposta bruta do gateway'
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagamento'
        verbose_name_plural = 'Pagamentos'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_method_display()} — Pedido #{self.order.order_id}'