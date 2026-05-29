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

    # EPUB (opcional)
    file_epub       = models.FileField(
        upload_to='protected/ebooks/epub/',
        blank=True, null=True,
        verbose_name='Arquivo EPUB'
    )
    # MOBI/Kindle (opcional)
    file_mobi       = models.FileField(
        upload_to='protected/ebooks/mobi/',
        blank=True, null=True,
        verbose_name='Arquivo MOBI (Kindle)'
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
    
    def get_available_formats(self):
        """Retorna lista de formatos disponíveis."""
        formats = ['PDF']
        if self.file_epub:
            formats.append('EPUB')
        if self.file_mobi:
            formats.append('MOBI')
        return formats

    def __str__(self):
        return self.title

class EbookBonus(models.Model):
    """
    eBook bônus vinculado a um eBook principal.
    Quem compra o principal recebe acesso aos bônus automaticamente.
    """

    ebook       = models.ForeignKey(
        Ebook,
        on_delete=models.CASCADE,
        related_name='bonuses',
        verbose_name='eBook principal'
    )
    title       = models.CharField(max_length=200, verbose_name='Título do bônus')
    description = models.TextField(blank=True, verbose_name='Descrição')
    cover       = models.ImageField(
        upload_to='covers/bonus/',
        blank=True, null=True,
        verbose_name='Capa do bônus'
    )

    # Arquivos do bônus
    file        = models.FileField(
        upload_to='protected/bonus/',
        verbose_name='Arquivo PDF',
        blank=True, null=True,
    )
    file_epub   = models.FileField(
        upload_to='protected/bonus/epub/',
        blank=True, null=True,
        verbose_name='Arquivo EPUB'
    )
    file_mobi   = models.FileField(
        upload_to='protected/bonus/mobi/',
        blank=True, null=True,
        verbose_name='Arquivo MOBI (Kindle)'
    )

    order       = models.PositiveIntegerField(
        default=0,
        verbose_name='Ordem de exibição'
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'eBook Bônus'
        verbose_name_plural = 'eBooks Bônus'
        ordering            = ['order', 'created_at']

    def get_available_formats(self):
        formats = []
        if self.file:
            formats.append('PDF')
        if self.file_epub:
            formats.append('EPUB')
        if self.file_mobi:
            formats.append('MOBI')
        return formats

    def __str__(self):
        return f'Bônus: {self.title} → {self.ebook.title}'