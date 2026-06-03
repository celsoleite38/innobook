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
    

    # ── Configuração da plataforma ──────────────────────────────
class PlatformConfig(models.Model):
    """
    Configurações globais da plataforma.
    Apenas um registro deve existir (singleton).
    """
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=10.00,
        verbose_name='Comissão da plataforma (%)'
    )
    min_withdraw      = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=50.00,
        verbose_name='Valor mínimo para saque (R$)'
    )
    withdraw_info     = models.TextField(
        blank=True,
        verbose_name='Instruções de saque',
        default='Os saques são processados em até 5 dias úteis via PIX.'
    )
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Configuração da Plataforma'
        verbose_name_plural = 'Configuração da Plataforma'

    def __str__(self):
        return f'Configuração — {self.commission_percent}% de comissão'

    @classmethod
    def get(cls):
        """Retorna a configuração singleton."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ── Dados bancários do produtor ─────────────────────────────
class ProducerBankData(models.Model):
    """Chave PIX do produtor para receber saques."""

    PIX_CPF     = 'cpf'
    PIX_CNPJ    = 'cnpj'
    PIX_EMAIL   = 'email'
    PIX_PHONE   = 'phone'
    PIX_RANDOM  = 'random'

    PIX_TYPES = [
        (PIX_CPF,    'CPF'),
        (PIX_CNPJ,   'CNPJ'),
        (PIX_EMAIL,  'Email'),
        (PIX_PHONE,  'Telefone'),
        (PIX_RANDOM, 'Chave aleatória'),
    ]

    producer  = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bank_data',
        verbose_name='Produtor'
    )
    pix_type  = models.CharField(
        max_length=20,
        choices=PIX_TYPES,
        verbose_name='Tipo de chave PIX'
    )
    pix_key   = models.CharField(
        max_length=200,
        verbose_name='Chave PIX'
    )
    full_name = models.CharField(
        max_length=200,
        verbose_name='Nome completo do titular'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Dados Bancários'
        verbose_name_plural = 'Dados Bancários'

    def __str__(self):
        return f'PIX de {self.producer.username}: {self.pix_key}'

# ── Solicitação de saque ─────────────────────────────────────
class WithdrawRequest(models.Model):
    """Solicitação de saque feita pelo produtor."""

    STATUS_PENDING  = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_PAID     = 'paid'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING,  'Aguardando aprovação'),
        (STATUS_APPROVED, 'Aprovado'),
        (STATUS_PAID,     'Pago'),
        (STATUS_REJECTED, 'Rejeitado'),
    ]

    producer    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='withdraw_requests',
        verbose_name='Produtor'
    )
    amount      = models.DecimalField(
        max_digits=8, decimal_places=2,
        verbose_name='Valor solicitado'
    )
    pix_key     = models.CharField(
        max_length=200,
        verbose_name='Chave PIX usada'
    )
    pix_type    = models.CharField(
        max_length=20,
        verbose_name='Tipo de chave PIX'
    )
    pix_holder  = models.CharField(
    max_length=200,
    blank=True,
    verbose_name='Nome do titular'
    )
    status      = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name='Status'
    )
    note        = models.TextField(
        blank=True,
        verbose_name='Observação do admin')
    
    receipt     = models.ImageField(
        upload_to='receipts/withdraws/',
        blank=True, null=True,
        verbose_name='Comprovante de pagamento'
    )

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    paid_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Solicitação de Saque'
        verbose_name_plural = 'Solicitações de Saque'
        ordering            = ['-created_at']

    def save(self, *args, **kwargs):
        from django.utils import timezone as tz
        # Marca como PAGO automaticamente quando comprovante for inserido
        if self.receipt and not self.paid_at:
            self.status  = self.STATUS_PAID
            self.paid_at = tz.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Saque R$ {self.amount} — {self.producer.username} — {self.get_status_display()}'