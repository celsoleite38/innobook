from django.db import models
from django.conf import settings
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Ex: 📚 ou classe CSS")

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Ebook(models.Model):

    STATUS_DRAFT     = 'draft'
    STATUS_PENDING   = 'pending'
    STATUS_PUBLISHED = 'published'
    STATUS_REJECTED  = 'rejected'

    STATUS_CHOICES = [
        (STATUS_DRAFT,     'Rascunho'),
        (STATUS_PENDING,   'Aguardando Aprovação'),
        (STATUS_PUBLISHED, 'Publicado'),
        (STATUS_REJECTED,  'Rejeitado'),
    ]

    # Relacionamentos
    author   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ebooks',
        verbose_name='Autor'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Categoria'
    )

    # Informações básicas
    title       = models.CharField(max_length=200, verbose_name='Título')
    slug        = models.SlugField(unique=True, blank=True, max_length=220)
    description = models.TextField(verbose_name='Descrição')
    cover       = models.ImageField(upload_to='covers/', verbose_name='Capa')

    # Arquivo protegido (PDF real — nunca público!)
    file        = models.FileField(
        upload_to='protected/ebooks/',
        verbose_name='Arquivo PDF'
    )

    # Preview gratuito (primeiras páginas)
    preview     = models.FileField(
        upload_to='previews/',
        blank=True, null=True,
        verbose_name='Preview gratuito'
    )

    # Preço e comercial
    price       = models.DecimalField(
        max_digits=8, decimal_places=2,
        verbose_name='Preço'
    )
    discount_price = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name='Preço promocional'
    )

    # Status e controle
    status      = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        verbose_name='Status'
    )
    pages       = models.PositiveIntegerField(null=True, blank=True, verbose_name='Páginas')
    language    = models.CharField(max_length=50, default='Português', verbose_name='Idioma')
    featured    = models.BooleanField(default=False, verbose_name='Destaque')

    # Datas
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'eBook'
        verbose_name_plural = 'eBooks'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_price(self):
        """Retorna o preço promocional se existir, senão o normal."""
        if self.discount_price:
            return self.discount_price
        return self.price

    def is_published(self):
        return self.status == self.STATUS_PUBLISHED

    def __str__(self):
        return self.title