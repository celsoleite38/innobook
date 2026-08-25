from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from apps.products.forms import EbookForm
from apps.products.models import Ebook


User = get_user_model()

DADOS_BASE = {
    'title': 'Livro de Teste',
    'description': 'Descrição',
    'price': '10.00',
    'language': 'Português',
}


def _make_ebook(author, **kwargs):
    defaults = dict(
        author=author,
        title='Livro de Teste',
        description='Descrição',
        cover=SimpleUploadedFile('capa.png', b'capa', content_type='image/png'),
        file=SimpleUploadedFile('livro.pdf', b'pdf', content_type='application/pdf'),
        price=Decimal('10.00'),
        status=Ebook.STATUS_PENDING,
    )
    defaults.update(kwargs)
    return Ebook.objects.create(**defaults)


class EbookFormArquivoAtualTests(TestCase):
    """Edição deve enxergar e permitir limpar arquivos já salvos."""

    def setUp(self):
        self.writer = User.objects.create_user(
            username='writer', password='senha123',
            email='writer@teste.com', role=User.PRODUCER,
            email_verified=True, producer_approved=True,
        )
        self.ebook = _make_ebook(self.writer)
        # Arquivo inválido gravado direto no banco (ex.: via /admin antigo),
        # burlando os validadores — como aconteceu com um JPG no campo EPUB.
        Ebook.objects.filter(pk=self.ebook.pk).update(
            file_epub='ebooks/epub/31EWY13fqaL._AC_.jpg'
        )
        self.ebook.refresh_from_db()

    def test_editar_sem_enviar_arquivo_aponta_erro_no_epub_invalido(self):
        form = EbookForm(DADOS_BASE, instance=self.ebook)
        self.assertFalse(form.is_valid())
        self.assertIn('file_epub', form.errors)
        self.assertIn('Formato não permitido', str(form.errors['file_epub']))

    def test_marcar_limpar_remove_epub_invalido_e_permite_salvar(self):
        dados = dict(DADOS_BASE, **{'file_epub-clear': 'on'})
        form = EbookForm(dados, instance=self.ebook)
        self.assertTrue(form.is_valid(), form.errors)
        ebook = form.save(commit=False)
        self.assertFalse(ebook.file_epub)

    def test_enviar_epub_valido_substitui_o_invalido(self):
        epub = SimpleUploadedFile('novo.epub', b'epub', content_type='application/epub+zip')
        form = EbookForm(DADOS_BASE, {'file_epub': epub}, instance=self.ebook)
        self.assertTrue(form.is_valid(), form.errors)
        ebook = form.save(commit=False)
        self.assertEqual(ebook.file_epub.name, 'novo.epub')

    def test_arquivos_validos_nao_bloqueiam_edicao(self):
        form = EbookForm(DADOS_BASE, instance=self.ebook)
        # sem mexer em nada relacionado a arquivos, o único erro é o epub
        self.assertEqual(list(form.errors.keys()), ['file_epub'])


class EbookValidacaoModeloTests(TestCase):
    """Validação de extensão no nível do modelo (vale para /admin e qualquer caminho)."""

    def setUp(self):
        self.writer = User.objects.create_user(
            username='writer2', password='senha123',
            email='writer2@teste.com', role=User.PRODUCER,
        )

    def test_full_clean_rejeita_extensao_invalida_no_epub(self):
        ebook = _make_ebook(
            self.writer,
            file_epub=SimpleUploadedFile('foto.jpg', b'jpg', content_type='image/jpeg'),
        )
        with self.assertRaises(ValidationError) as ctx:
            ebook.full_clean()
        self.assertIn('file_epub', ctx.exception.error_dict)

    def test_full_clean_aceita_formatos_validos(self):
        ebook = _make_ebook(
            self.writer,
            file_mobi=SimpleUploadedFile('livro.mobi', b'mobi', content_type='application/x-mobipocket-ebook'),
        )
        try:
            ebook.full_clean()
        except ValidationError as e:
            self.fail(f'full_clean deveria passar: {e.error_dict}')


class PrecoMinimoTests(TestCase):
    """Trava de preço mínimo (R$ 5,90) e promoção < preço normal."""

    def setUp(self):
        self.writer = User.objects.create_user(
            username='writer3', password='senha123',
            email='writer3@teste.com', role=User.PRODUCER,
        )

    @staticmethod
    def _dados(**extras):
        buffer = BytesIO()
        Image.new('RGB', (1, 1)).save(buffer, format='PNG')
        arquivos = {
            'cover': SimpleUploadedFile('capa.png', buffer.getvalue(), content_type='image/png'),
            'file': SimpleUploadedFile('livro.pdf', b'pdf', content_type='application/pdf'),
        }
        return dict(DADOS_BASE, **extras), arquivos

    def test_form_rejeita_preco_abaixo_do_minimo(self):
        dados, extras = self._dados(price='5.89')
        form = EbookForm(dados, extras)
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)
        self.assertIn('5.9', str(form.errors['price']))

    def test_form_rejeita_preco_promocional_abaixo_do_minimo(self):
        dados, extras = self._dados(discount_price='1.00')
        form = EbookForm(dados, extras)
        self.assertFalse(form.is_valid())
        self.assertIn('discount_price', form.errors)

    def test_form_rejeita_preco_fisico_e_combo_abaixo_do_minimo(self):
        dados, extras = self._dados(physical_price='0.00', combo_price='-3.00')
        form = EbookForm(dados, extras)
        self.assertFalse(form.is_valid())
        self.assertIn('physical_price', form.errors)
        self.assertIn('combo_price', form.errors)

    def test_form_rejeita_promocional_maior_ou_igual_ao_preco_normal(self):
        for desconto in ('10.00', '15.00'):
            dados, extras = self._dados(discount_price=desconto)
            form = EbookForm(dados, extras)
            self.assertFalse(form.is_valid(), f'desconto={desconto} deveria ser rejeitado')
            self.assertIn('discount_price', form.errors)
            self.assertIn(
                'menor que o preço normal',
                str(form.errors['discount_price']),
            )

    def test_modelo_rejeita_preco_abaixo_do_minimo_no_full_clean(self):
        ebook = _make_ebook(self.writer, price=Decimal('2.50'))
        with self.assertRaises(ValidationError) as ctx:
            ebook.full_clean()
        self.assertIn('price', ctx.exception.error_dict)

    def test_valores_no_limite_sao_aceitos(self):
        dados, extras = self._dados(
            discount_price='5.90',
            physical_price='6.00',
            combo_price='7.00',
        )
        form = EbookForm(dados, extras)
        self.assertTrue(form.is_valid(), form.errors)
