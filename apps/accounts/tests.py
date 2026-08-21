from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.payments.models import PlatformConfig
from apps.products.models import Ebook


User = get_user_model()


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


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ModerationFlowTests(TestCase):
    """Fluxo: staff rejeita com justificativa → escritor edita → volta a pendente."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='staff', password='senha123',
            email='staff@teste.com', is_staff=True,
        )
        self.writer = User.objects.create_user(
            username='writer', password='senha123',
            email='writer@teste.com', role=User.PRODUCER,
            email_verified=True, producer_approved=True,
        )
        self.ebook = _make_ebook(self.writer)

    def _login(self, user):
        """Login contornando o TwoFactorVerificationMiddleware."""
        self.client.force_login(user)
        session = self.client.session
        session['two_factor_verified'] = True
        session.save()

    def test_rejeitar_sem_justificativa_bloqueia(self):
        self._login(self.staff)
        resp = self.client.post(
            reverse('accounts:admin_book_reject', args=[self.ebook.pk]),
            {'justificativa': '   '},
        )
        self.ebook.refresh_from_db()
        self.assertEqual(self.ebook.status, Ebook.STATUS_PENDING)
        self.assertEqual(self.ebook.rejection_reason, '')
        self.assertEqual(len(mail.outbox), 0)

    def test_rejeitar_com_justificativa_salva_e_envia_email(self):
        self._login(self.staff)
        resp = self.client.post(
            reverse('accounts:admin_book_reject', args=[self.ebook.pk]),
            {'justificativa': 'Capa com baixa resolução.'},
        )
        self.ebook.refresh_from_db()
        self.assertEqual(self.ebook.status, Ebook.STATUS_REJECTED)
        self.assertEqual(self.ebook.rejection_reason, 'Capa com baixa resolução.')
        self.assertEqual(len(mail.outbox), 1)
        corpo = mail.outbox[0].body
        self.assertIn('Capa com baixa resolução.', corpo)
        self.assertIn(self.ebook.title, corpo)
        self.assertIn(self.writer.email, mail.outbox[0].to)

    def test_aprovar_limpa_justificativa(self):
        self.ebook.status = Ebook.STATUS_REJECTED
        self.ebook.rejection_reason = 'Problema X'
        self.ebook.save()

        self._login(self.staff)
        self.client.post(reverse('accounts:admin_book_approve', args=[self.ebook.pk]))

        self.ebook.refresh_from_db()
        self.assertEqual(self.ebook.status, Ebook.STATUS_PUBLISHED)
        self.assertEqual(self.ebook.rejection_reason, '')

    def test_editar_rejeitado_volta_para_pendente(self):
        self.ebook.status = Ebook.STATUS_REJECTED
        self.ebook.rejection_reason = 'Corrija o texto.'
        self.ebook.save()

        self._login(self.writer)
        resp = self.client.post(
            reverse('accounts:ebook_edit', args=[self.ebook.pk]),
            {
                'title': 'Livro de Teste (revisado)',
                'description': 'Descrição corrigida.',
                'price': '10.00',
                'language': 'Português',
            },
        )
        self.ebook.refresh_from_db()
        self.assertEqual(self.ebook.status, Ebook.STATUS_PENDING)
        self.assertEqual(self.ebook.rejection_reason, '')
        self.assertEqual(self.ebook.title, 'Livro de Teste (revisado)')

    def test_publicar_direto_bloqueado_para_rejeitado(self):
        config = PlatformConfig.get()
        config.terms_enabled = True
        config.save()
        self.writer.terms_accepted = True
        self.writer.save()

        self.ebook.status = Ebook.STATUS_REJECTED
        self.ebook.rejection_reason = 'Pendência.'
        self.ebook.save()

        self._login(self.writer)
        resp = self.client.post(
            reverse('accounts:producer_book_publish', args=[self.ebook.pk]),
        )
        self.ebook.refresh_from_db()
        self.assertEqual(self.ebook.status, Ebook.STATUS_REJECTED)

    def test_dashboard_mostra_justificativa(self):
        self.ebook.status = Ebook.STATUS_REJECTED
        self.ebook.rejection_reason = 'Revise o arquivo PDF.'
        self.ebook.save()

        self._login(self.writer)
        resp = self.client.get(reverse('accounts:producer'))
        self.assertContains(resp, 'Revise o arquivo PDF.')
