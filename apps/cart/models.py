from django.db import models
from django.conf import settings
from apps.products.models import Ebook, FORMAT_CHOICES, FORMAT_DIGITAL


class Cart(models.Model):
    """Carrinho de compras do usuário."""
    user       = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Carrinho'
        verbose_name_plural = 'Carrinhos'

    @property
    def total(self):
        return sum(item.price for item in self.items.all())

    @property
    def count(self):
        return self.items.count()

    def __str__(self):
        return f'Carrinho de {self.user.username}'


class CartItem(models.Model):
    """Item dentro do carrinho."""
    cart       = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    ebook      = models.ForeignKey(Ebook, on_delete=models.CASCADE)
    variant    = models.CharField(
        max_length=20,
        choices=FORMAT_CHOICES,
        default=FORMAT_DIGITAL,
        verbose_name='Formato'
    )
    added_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Item do Carrinho'
        unique_together = ['cart', 'ebook', 'variant']  # não duplica formato

    @property
    def price(self):
        return self.ebook.get_format_price(self.variant)

    def __str__(self):
        return f'{self.ebook.title} ({self.get_variant_display()}) — {self.cart.user.username}'