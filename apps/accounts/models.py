from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .validators import validar_cpf


class User(AbstractUser):

    BUYER = 'buyer'
    PRODUCER = 'producer'
    ROLE_CHOICES = [
        (BUYER, 'Comprador'),
        (PRODUCER, 'Produtor'),
    ]

    role   = models.CharField(max_length=20, choices=ROLE_CHOICES, default=BUYER)
    bio    = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    cpf    = models.CharField(
        max_length=14,
        unique=True,
        null=True,
        blank=True,
        validators=[validar_cpf],
        verbose_name='CPF',
    )

    # Segurança da conta
    email_verified    = models.BooleanField(default=False, verbose_name='E-mail verificado')
    two_factor_enabled = models.BooleanField(default=False, verbose_name='2FA ativo')

    # Produtor
    producer_requested = models.BooleanField(default=False, verbose_name='Solicitou ser produtor')
    producer_approved  = models.BooleanField(default=False, verbose_name='Produtor aprovado')

    # Proteção contra força bruta
    failed_login_count = models.PositiveIntegerField(default=0, verbose_name='Tentativas de login falhas')
    locked_until       = models.DateTimeField(null=True, blank=True, verbose_name='Bloqueado até')

    @property
    def cpf_formatado(self):
        """Retorna CPF formatado para exibição"""
        cpf = self.cpf or ''
        if len(cpf) != 11:
            return cpf
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def is_producer(self):
        return self.role == self.PRODUCER

    def is_producer_active(self):
        return (
            self.role == self.PRODUCER
            and self.producer_approved
            and self.email_verified
        )

    def __str__(self):
        return self.email
