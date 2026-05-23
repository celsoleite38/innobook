from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


def send_purchase_confirmation(order, token):
    """
    Envia email de confirmação de compra com link de download.
    """
    subject = f'✅ Compra confirmada — {order.ebook.title}'

    context = {
        'order': order,
        'token': token,
    }

    html_message = render_to_string('emails/purchase_confirmation.html', context)
    plain_message = render_to_string('emails/purchase_confirmation.txt', context)

    send_mail(
        subject      = subject,
        message      = plain_message,
        from_email   = settings.DEFAULT_FROM_EMAIL,
        recipient_list = [order.buyer_email],
        html_message = html_message,
        fail_silently = False,
    )


def send_new_sale_notification(order):
    """
    Notifica o produtor sobre uma nova venda.
    """
    subject = f'🎉 Nova venda — {order.ebook.title}'

    context = {'order': order}

    html_message  = render_to_string('emails/new_sale.html', context)
    plain_message = render_to_string('emails/new_sale.txt', context)

    send_mail(
        subject        = subject,
        message        = plain_message,
        from_email     = settings.DEFAULT_FROM_EMAIL,
        recipient_list = [order.ebook.author.email],
        html_message   = html_message,
        fail_silently  = True,  # não quebra o fluxo se o produtor não tiver email
    )