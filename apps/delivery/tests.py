import base64
import hashlib
import hmac

from django.test import TestCase, override_settings

from .melhor_envios import (
    verify_webhook_signature,
    map_webhook_event,
    MelhorEnviosError,
)


@override_settings(ME_WEBHOOK_TOKEN='secret-token')
class WebhookSignatureTests(TestCase):

    def test_assinatura_valida(self):
        body = b'{"event": "order.posted", "data": {"id": "1"}}'
        signature = base64.b64encode(
            hmac.new(b'secret-token', body, hashlib.sha256).digest()
        ).decode()
        self.assertTrue(verify_webhook_signature(body, signature))

    def test_assinatura_invalida(self):
        self.assertFalse(verify_webhook_signature(b'corpo', 'assinatura-errada'))

    def test_sem_token_rejeita(self):
        self.assertFalse(verify_webhook_signature(b'corpo', 'qualquer'))


class EventMappingTests(TestCase):

    def test_eventos_mapeados(self):
        self.assertEqual(map_webhook_event('order.posted'), 'shipped')
        self.assertEqual(map_webhook_event('order.delivered'), 'delivered')
        self.assertEqual(map_webhook_event('order.cancelled'), 'cancelled')
        self.assertEqual(map_webhook_event('order.undelivered'), 'cancelled')

    def test_eventos_ignorados(self):
        self.assertIsNone(map_webhook_event('order.created'))
        self.assertIsNone(map_webhook_event('unknown'))


class CalcularFreteTests(TestCase):

    @override_settings(ME_CLIENT_ID='', ME_CLIENT_SECRET='')
    def test_erro_sem_configuracao(self):
        """Sem credenciais no .env, get_token levanta MelhorEnviosError."""
        from apps.accounts.models import User
        from .melhor_envios import get_token

        producer = User.objects.create_user(username='autor', password='x')
        with self.assertRaises(MelhorEnviosError):
            get_token(producer)


@override_settings(ME_CLIENT_ID='id', ME_CLIENT_SECRET='sec', ME_ENV='sandbox')
class GetTokenRouterTests(TestCase):
    """get_token roteia para a conta da Editora (padrão) ou a do escritor."""

    def setUp(self):
        from django.utils import timezone
        from datetime import timedelta
        from apps.accounts.models import User
        from .models import ShippingProfile

        self.producer = User.objects.create_user(username='autor', password='x')
        self.profile = ShippingProfile.objects.create(
            producer=self.producer,
            me_access_token='proprio-tok',
            me_refresh_token='proprio-ref',
            me_expires_at=timezone.now() + timedelta(days=30),
        )

    def test_conta_editora_usada_quando_flag_true(self):
        from django.utils import timezone
        from datetime import timedelta
        from .models import EditoraShippingAccount
        from .melhor_envios import get_token

        EditoraShippingAccount.objects.create(
            holder_name='Editora',
            me_access_token='editora-tok',
            me_refresh_token='editora-ref',
            me_expires_at=timezone.now() + timedelta(days=30),
        )
        self.profile.uses_editora_account = True
        self.profile.save()
        self.assertEqual(get_token(self.producer), 'editora-tok')

    def test_conta_propria_usada_quando_flag_false(self):
        from .melhor_envios import get_token

        self.profile.uses_editora_account = False
        self.profile.save()
        self.assertEqual(get_token(self.producer), 'proprio-tok')

    def test_erro_quando_editora_nao_conectada(self):
        from .melhor_envios import get_token, MelhorEnviosError

        self.profile.uses_editora_account = True
        self.profile.save()
        with self.assertRaises(MelhorEnviosError):
            get_token(self.producer)

    def test_erro_quando_conta_propria_nao_conectada(self):
        from .melhor_envios import get_token, MelhorEnviosError

        self.profile.uses_editora_account = False
        self.profile.me_access_token = ''
        self.profile.me_refresh_token = ''
        self.profile.save()
        with self.assertRaises(MelhorEnviosError):
            get_token(self.producer)


@override_settings(ME_CLIENT_ID='id', ME_CLIENT_SECRET='sec', ME_ENV='sandbox')
class ShippingReadyTests(TestCase):
    """Prontidão para envios: remetente + (conta própria OU conta da Editora)."""

    def setUp(self):
        from apps.accounts.models import User
        from .models import ShippingProfile

        self.producer = User.objects.create_user(username='autor', password='x')
        self.profile = ShippingProfile.objects.create(
            producer=self.producer,
            full_name='Autor', document='52998224725', phone='11999999999',
            zipcode='01001000', address='Rua A', number='10',
            district='Centro', city='São Paulo', state='SP',
            me_access_token='tok', me_refresh_token='ref',
        )

    def test_pronto_via_conta_propria(self):
        from .melhor_envios import shipping_ready, shipping_ready_error

        self.profile.uses_editora_account = False
        self.profile.save()
        self.assertIsNone(shipping_ready_error(self.producer))
        self.assertTrue(shipping_ready(self.producer))

    def test_pronto_via_conta_editora(self):
        from django.utils import timezone
        from datetime import timedelta
        from .models import EditoraShippingAccount
        from .melhor_envios import shipping_ready, shipping_ready_error

        EditoraShippingAccount.objects.create(
            holder_name='Editora',
            me_access_token='tok', me_refresh_token='ref',
            me_expires_at=timezone.now() + timedelta(days=30),
        )
        self.assertIsNone(shipping_ready_error(self.producer))
        self.assertTrue(shipping_ready(self.producer))

    def test_bloqueado_sem_editora_conectada(self):
        from .melhor_envios import shipping_ready_error

        self.assertIn(
            'conta Melhor Envios da Editora',
            shipping_ready_error(self.producer),
        )

    def test_bloqueado_sem_endereco_de_remetente(self):
        from .melhor_envios import shipping_ready_error

        self.profile.address = ''
        self.profile.save()
        self.assertIn('remetente', shipping_ready_error(self.producer))

    def test_bloqueado_sem_conta_propria_conectada(self):
        from .melhor_envios import shipping_ready_error

        self.profile.uses_editora_account = False
        self.profile.me_access_token = ''
        self.profile.me_refresh_token = ''
        self.profile.save()
        self.assertIn('não conectou', shipping_ready_error(self.producer))
