from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator

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
    cpf    = models.CharField(max_length=11,  # Salva apenas números
        #unique=True,
        validators=[
            RegexValidator(
                regex=r'^\d{11}$',
                message='CPF deve conter 11 dígitos numéricos'
            )
        ]
    )
    
    @property
    def cpf_formatado(self):
        """Retorna CPF formatado para exibição"""
        cpf = self.cpf
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

    def is_producer(self):
        return self.role == self.PRODUCER

    def __str__(self):
        return self.email