from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from core.storages import ProtectedFileSystemStorage

protected_storage = ProtectedFileSystemStorage()


# Formatos de compra
FORMAT_DIGITAL  = 'digital'
FORMAT_PHYSICAL = 'physical'
FORMAT_COMBO    = 'combo'

FORMAT_CHOICES = [
    (FORMAT_DIGITAL,  'Digital'),
    (FORMAT_PHYSICAL, 'Físico'),
    (FORMAT_COMBO,    'Físico + Digital'),
]


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

    # ISBN por formato
    isbn_physical = models.CharField(
        max_length=13, blank=True, null=True, verbose_name='ISBN Físico',
        help_text='ISBN da versão física. Obrigatório se o arquivo físico for enviado.'
    )
    isbn_pdf = models.CharField(
        max_length=13, blank=True, null=True, verbose_name='ISBN PDF',
        help_text='ISBN da versão PDF. Obrigatório se o arquivo PDF for enviado.'
    )
    isbn_epub = models.CharField(
        max_length=13, blank=True, null=True, verbose_name='ISBN EPUB',
        help_text='ISBN da versão EPUB. Obrigatório se o arquivo EPUB for enviado.'
    )
    isbn_mobi = models.CharField(
        max_length=13, blank=True, null=True, verbose_name='ISBN MOBI (Kindle)',
        help_text='ISBN da versão MOBI. Obrigatório se o arquivo MOBI for enviado.'
    )

    # Arquivo protegido (PDF real — nunca público! fica fora do MEDIA_ROOT)
    file        = models.FileField(
        storage=protected_storage,
        upload_to='ebooks/',
        blank=True, null=True,
        verbose_name='Arquivo PDF'
    )

    # EPUB (opcional)
    file_epub       = models.FileField(
        storage=protected_storage,
        upload_to='ebooks/epub/',
        blank=True, null=True,
        verbose_name='Arquivo EPUB'
    )
    # MOBI/Kindle (opcional)
    file_mobi       = models.FileField(
        storage=protected_storage,
        upload_to='ebooks/mobi/',
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
        null=True, blank=True,
        verbose_name='Preço digital'
    )
    discount_price = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name='Preço promocional'
    )

    # Livro físico (impresso)
    physical_price = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name='Preço do livro físico'
    )
    combo_price = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name='Preço físico + digital (combo)'
    )
    physical_stock = models.PositiveIntegerField(
        default=0,
        verbose_name='Estoque físico'
    )

    # Dados de embalagem (para cotação de frete)
    physical_weight_g = models.PositiveIntegerField(
        default=300,
        verbose_name='Peso físico (gramas)',
        help_text='Peso do livro físico embalado, em gramas.'
    )
    physical_length_cm = models.DecimalField(
        max_digits=5, decimal_places=2, default=16,
        verbose_name='Comprimento (cm)'
    )
    physical_width_cm = models.DecimalField(
        max_digits=5, decimal_places=2, default=16,
        verbose_name='Largura (cm)'
    )
    physical_height_cm = models.DecimalField(
        max_digits=5, decimal_places=2, default=2,
        verbose_name='Altura (cm)'
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

    def clean(self):
        """Valida: ao menos 1 formato (digital ou físico); ISBNs obrigatórios."""
        super().clean()
        errors = {}

        # Pelo menos um formato deve ser oferecido
        has_digital  = bool(self.file or self.file_epub or self.file_mobi)
        has_physical = bool(self.physical_price)
        if not has_digital and not has_physical:
            errors['__all__'] = (
                'Envie pelo menos um arquivo digital (PDF, EPUB ou MOBI) '
                'ou informe o preço físico.'
            )

        isbn_map = {
            'isbn_pdf': ('file', 'PDF'),
            'isbn_epub': ('file_epub', 'EPUB'),
            'isbn_mobi': ('file_mobi', 'MOBI'),
            'isbn_physical': ('physical_price', 'Físico'),
        }

        for isbn_field, (file_field, label) in isbn_map.items():
            isbn_value = getattr(self, isbn_field, '').strip() if getattr(self, isbn_field, '') else ''
            file_value = getattr(self, file_field, None)

            if file_value and not isbn_value:
                errors[isbn_field] = f'O ISBN {label} é obrigatório quando o arquivo é enviado.'
            if isbn_value and len(isbn_value) not in (10, 13):
                errors[isbn_field] = f'O ISBN {label} deve ter 10 ou 13 caracteres.'

        all_isbn_fields = ['isbn_physical', 'isbn_pdf', 'isbn_epub', 'isbn_mobi']
        for isbn_field in all_isbn_fields:
            isbn_value = getattr(self, isbn_field, '').strip() if getattr(self, isbn_field, '') else ''
            if not isbn_value:
                continue

            qs = Ebook.objects.filter(**{isbn_field: isbn_value})
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                errors[isbn_field] = f'Este ISBN já está em uso em outro eBook.'

            check_fields = [f for f in all_isbn_fields if f != isbn_field]
            for other_field in check_fields:
                other_qs = Ebook.objects.filter(**{other_field: isbn_value})
                if self.pk:
                    other_qs = other_qs.exclude(pk=self.pk)
                if other_qs.exists():
                    errors[isbn_field] = f'Este ISBN já está cadastrado no campo {other_field} de outro eBook.'
                    break

        if errors:
            raise ValidationError(errors)

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
        formats = []
        if self.file:
            formats.append('PDF')
        if self.file_epub:
            formats.append('EPUB')
        if self.file_mobi:
            formats.append('MOBI')
        return formats

    def has_physical(self):
        return bool(self.physical_price and self.physical_stock)

    def physical_dimensions(self):
        """Retorna (comprimento, largura, altura, peso_g) ou None se incompleto."""
        if not all([self.physical_length_cm, self.physical_width_cm,
                    self.physical_height_cm, self.physical_weight_g]):
            return None
        return (
            float(self.physical_length_cm),
            float(self.physical_width_cm),
            float(self.physical_height_cm),
            self.physical_weight_g,
        )

    def get_combo_price(self):
        """Preço do combo físico + digital (ou soma dos dois)."""
        if self.combo_price:
            return self.combo_price
        return (self.physical_price or 0) + (self.get_price() or 0)

    def get_format_price(self, variant):
        """Retorna o preço de um formato de compra específico."""
        if variant == FORMAT_PHYSICAL:
            return self.physical_price or 0
        if variant == FORMAT_COMBO:
            return self.get_combo_price()
        return self.get_price()

    def get_format_label(self, variant):
        for value, label in FORMAT_CHOICES:
            if value == variant:
                return label
        return 'Digital'

    def user_owns_format(self, user, variant):
        """True se o usuário já comprou acesso ao formato solicitado."""
        from apps.payments.models import Order
        paid = user.orders.filter(ebook=self, status=Order.STATUS_PAID)
        if variant == FORMAT_COMBO:
            return paid.filter(variant=FORMAT_COMBO).exists()
        if variant == FORMAT_PHYSICAL:
            return paid.filter(variant__in=[FORMAT_PHYSICAL, FORMAT_COMBO]).exists()
        return paid.filter(variant__in=[FORMAT_DIGITAL, FORMAT_COMBO]).exists()

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

    # Arquivos do bônus (protegidos — fora do MEDIA_ROOT)
    file        = models.FileField(
        storage=protected_storage,
        upload_to='bonus/',
        verbose_name='Arquivo PDF',
        blank=True, null=True,
    )
    file_epub   = models.FileField(
        storage=protected_storage,
        upload_to='bonus/epub/',
        blank=True, null=True,
        verbose_name='Arquivo EPUB'
    )
    file_mobi   = models.FileField(
        storage=protected_storage,
        upload_to='bonus/mobi/',
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