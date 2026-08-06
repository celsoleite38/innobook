from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from unittest import mock

from apps.products.models import Ebook, FORMAT_PHYSICAL
from apps.cart.models import Cart, CartItem
from apps.delivery.models import ShippingProfile, Shipment
from .models import Order, WithdrawRequest


User = get_user_model()
CPF_AUTOR = '52998224725'
CPF_COMPRADOR = '11144477735'


def _make_user(username, role, cpf):
    return User.objects.create_user(
        username=username,
        password='senha123',
        email=f'{username}@teste.com',
        role=role,
        cpf=cpf,
    )


def _make_ebook(author):
    return Ebook.objects.create(
        author=author,
        title='Livro Físico de Teste',
        description='Descrição',
        cover=SimpleUploadedFile('capa.png', b'capa', content_type='image/png'),
        file=SimpleUploadedFile('livro.pdf', b'pdf', content_type='application/pdf'),
        price=Decimal('10.00'),
        physical_price=Decimal('30.00'),
        physical_stock=5,
        physical_weight_g=300,
        physical_length_cm=16,
        physical_width_cm=16,
        physical_height_cm=2,
        status=Ebook.STATUS_PUBLISHED,
    )


@override_settings(ME_CLIENT_ID='id', ME_CLIENT_SECRET='sec', ME_ENV='sandbox')
class OrderModelTests(TestCase):
    def setUp(self):
        self.autor = _make_user('autor', User.PRODUCER, CPF_AUTOR)
        self.buyer = _make_user('comprador', User.BUYER, CPF_COMPRADOR)
        self.ebook = _make_ebook(self.autor)

    def test_total_com_frete(self):
        order = Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), shipping_cost=Decimal('15.50'),
            status=Order.STATUS_PAID, buyer_email=self.buyer.email,
            buyer_name='Comprador',
        )
        self.assertEqual(order.total_with_shipping, Decimal('45.50'))

    def test_aprovado_nao_desconta_do_disponivel(self):
        from apps.payments.finance import get_producer_financial
        # Conta própria → o frete é creditado ao escritor
        ShippingProfile.objects.create(
            producer=self.autor,
            me_access_token='tok', me_refresh_token='ref',
            uses_editora_account=False,
        )
        Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), shipping_cost=Decimal('15.50'),
            status=Order.STATUS_PAID, buyer_email=self.buyer.email,
            buyer_name='Comprador',
        )
        WithdrawRequest.objects.create(
            producer=self.autor, amount=Decimal('10.00'),
            pix_key='key', pix_type='email', status=WithdrawRequest.STATUS_APPROVED,
        )
        financial = get_producer_financial(self.autor)
        self.assertEqual(financial['total_withdrawn'], Decimal('0'))
        self.assertEqual(financial['available'], Decimal('42.50'))

    def test_pago_desconta_do_disponivel(self):
        from apps.payments.finance import get_producer_financial
        ShippingProfile.objects.create(
            producer=self.autor,
            me_access_token='tok', me_refresh_token='ref',
            uses_editora_account=False,
        )
        Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), shipping_cost=Decimal('15.50'),
            status=Order.STATUS_PAID, buyer_email=self.buyer.email,
            buyer_name='Comprador',
        )
        WithdrawRequest.objects.create(
            producer=self.autor, amount=Decimal('10.00'),
            pix_key='key', pix_type='email', status=WithdrawRequest.STATUS_PAID,
        )
        financial = get_producer_financial(self.autor)
        self.assertEqual(financial['total_withdrawn'], Decimal('10.00'))
        self.assertEqual(financial['available'], Decimal('32.50'))

    def test_conta_editora_nao_credita_frete(self):
        """Padrão (conta da Editora): frete não entra no saldo do escritor."""
        from apps.payments.finance import get_producer_financial
        ShippingProfile.objects.create(
            producer=self.autor,
            full_name='Autor', zipcode='01001000', address='Rua A', number='10',
            district='Centro', city='São Paulo', state='SP',
            me_access_token='tok', me_refresh_token='ref',
            uses_editora_account=True,
        )
        Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), shipping_cost=Decimal('15.50'),
            status=Order.STATUS_PAID, buyer_email=self.buyer.email,
            buyer_name='Comprador',
        )
        financial = get_producer_financial(self.autor)
        self.assertEqual(financial['total_shipping'], Decimal('0'))
        # líquido 30 − 10% = 27, sem frete
        self.assertEqual(financial['available'], Decimal('27.00'))

    def test_conta_propria_credita_frete(self):
        from apps.payments.finance import get_producer_financial
        ShippingProfile.objects.create(
            producer=self.autor,
            full_name='Autor', zipcode='01001000', address='Rua A', number='10',
            district='Centro', city='São Paulo', state='SP',
            me_access_token='tok', me_refresh_token='ref',
            uses_editora_account=False,
        )
        Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), shipping_cost=Decimal('15.50'),
            status=Order.STATUS_PAID, buyer_email=self.buyer.email,
            buyer_name='Comprador',
        )
        financial = get_producer_financial(self.autor)
        self.assertEqual(financial['total_shipping'], Decimal('15.50'))
        self.assertEqual(financial['available'], Decimal('42.50'))

    def test_cancelamento_permitido_antes_da_postagem(self):
        order = Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), status=Order.STATUS_PAID,
            buyer_email=self.buyer.email, buyer_name='Comprador',
        )
        self.assertTrue(order.can_cancel_shipping())

    def test_cancelamento_bloqueado_apos_envio(self):
        order = Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), status=Order.STATUS_PAID,
            shipping_status=Order.SHIPPING_SHIPPED,
            buyer_email=self.buyer.email, buyer_name='Comprador',
        )
        self.assertFalse(order.can_cancel_shipping())

    def test_cancelamento_bloqueado_quando_etiqueta_gerada(self):
        """Comprador não pode cancelar após a etiqueta ser gerada (status ready)."""
        order = Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), status=Order.STATUS_PAID,
            shipping_status=Order.SHIPPING_READY,
            buyer_email=self.buyer.email, buyer_name='Comprador',
        )
        self.assertFalse(order.can_cancel_shipping())


@override_settings(
    ME_CLIENT_ID='id', ME_CLIENT_SECRET='sec', ME_ENV='sandbox',
    ASAAS_API_KEY='chave-teste',
)
class CartCheckoutFreightTests(TestCase):
    """Checkout do carrinho cobra produto + frete e cria o pacote."""

    def setUp(self):
        self.autor = _make_user('autor', User.PRODUCER, CPF_AUTOR)
        self.buyer = _make_user('comprador', User.BUYER, CPF_COMPRADOR)
        self.ebook = _make_ebook(self.autor)

        # Perfil de envio do escritor conectado (conta própria → frete do escritor)
        self.profile = ShippingProfile.objects.create(
            producer=self.autor,
            full_name='Autor', document=CPF_AUTOR, phone='11999999999',
            zipcode='01001000', address='Rua A', number='10',
            district='Centro', city='São Paulo', state='SP',
            me_access_token='tok', me_refresh_token='ref',
            uses_editora_account=False,
        )

        self.cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=self.cart, ebook=self.ebook, variant=FORMAT_PHYSICAL)

        self.offer = {
            'id': '4', 'name': 'Correios PAC', 'company_name': 'Correios',
            'price': '15.90', 'delivery_time': 7, 'packages': [
                {'height': 2, 'width': 16, 'length': 16, 'weight': 0.3},
            ],
        }

    @mock.patch('apps.payments.views.create_charge')
    @mock.patch('apps.payments.views.get_pix_qrcode')
    @mock.patch('apps.delivery.melhor_envios.calcular_frete')
    def test_checkout_cria_pedido_pacote_e_cobra_total(self, mock_frete, mock_pix, mock_charge):
        mock_frete.return_value = [self.offer]
        mock_charge.return_value = {'id': 'pay_123', 'invoiceUrl': ''}
        mock_pix.return_value = {'encodedImage': '', 'payload': '', 'expirationDate': ''}

        self.client.force_login(self.buyer)

        response = self.client.post('/payments/checkout/carrinho/', {
            'shipping_name': 'Comprador',
            'shipping_zipcode': '20040020',
            'shipping_address': 'Rua B',
            'shipping_number': '5',
            'shipping_district': 'Centro',
            'shipping_complement': '',
            'shipping_city': 'Rio de Janeiro',
            'shipping_state': 'RJ',
            'billing_type': 'PIX',
            'offer_{}'.format(self.autor.id): '4',
        }, follow=True)

        # Renderiza a página PIX
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.templates[0].name, 'payments/pix.html')

        # Charge cobrou produto + frete
        self.assertEqual(
            mock_charge.call_args[1]['value'],
            Decimal('45.90'),
        )

        # Pedido com frete e pacote vinculado
        order = Order.objects.get(ebook=self.ebook, buyer=self.buyer)
        self.assertEqual(order.shipping_cost, Decimal('15.90'))
        self.assertEqual(order.amount, Decimal('30.00'))
        self.assertIsNotNone(order.shipment)

        shipment = Shipment.objects.get(producer=self.autor)
        self.assertEqual(shipment.status, Shipment.STATUS_AWAITING)
        self.assertEqual(shipment.freight_cost, Decimal('15.90'))
        self.assertEqual(shipment.offer_id, '4')
        self.assertEqual(shipment.orders.count(), 1)

    @mock.patch('apps.delivery.melhor_envios.calcular_frete')
    def test_checkout_rejeita_sem_transportadora(self, mock_frete):
        mock_frete.return_value = [self.offer]
        self.client.force_login(self.buyer)

        response = self.client.post('/payments/checkout/carrinho/', {
            'shipping_name': 'Comprador',
            'shipping_zipcode': '20040020',
            'shipping_address': 'Rua B',
            'shipping_number': '5',
            'shipping_district': 'Centro',
            'shipping_city': 'Rio de Janeiro',
            'shipping_state': 'RJ',
            'billing_type': 'PIX',
        }, follow=True)

        self.assertFalse(Order.objects.filter(buyer=self.buyer).exists())
        self.assertContains(response, 'Selecione a transportadora')


@override_settings(ME_CLIENT_ID='id', ME_CLIENT_SECRET='sec', ME_ENV='sandbox')
class BuyerCancelShippingTests(TestCase):
    """Comprador não cancela pacote com etiqueta já gerada (janela de postagem)."""

    def setUp(self):
        self.autor = _make_user('autor', User.PRODUCER, CPF_AUTOR)
        self.buyer = _make_user('comprador', User.BUYER, CPF_COMPRADOR)
        self.ebook = _make_ebook(self.autor)

        self.shipment = Shipment.objects.create(
            producer=self.autor, buyer=self.buyer,
            status=Shipment.STATUS_READY, freight_cost=Decimal('15.90'),
        )
        self.order = Order.objects.create(
            buyer=self.buyer, ebook=self.ebook, variant=FORMAT_PHYSICAL,
            amount=Decimal('30.00'), shipping_cost=Decimal('15.90'),
            status=Order.STATUS_PAID, shipping_status=Order.SHIPPING_READY,
            shipment=self.shipment,
            buyer_email=self.buyer.email, buyer_name='Comprador',
        )

    @mock.patch('apps.delivery.views.cancel_shipment')
    def test_cancelar_bloqueado_apos_etiqueta(self, mock_cancel):
        self.client.force_login(self.buyer)
        response = self.client.post(
            '/payments/meus-pedidos/{}/cancelar-envio/'.format(self.order.order_id),
            follow=True,
        )

        mock_cancel.assert_not_called()
        self.assertContains(response, 'etiqueta gerada')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_PAID)
        self.assertEqual(self.shipment.status, Shipment.STATUS_READY)
