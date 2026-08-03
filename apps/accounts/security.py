import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
OTP_VALID_MINUTES = 10
MAX_OTP_ATTEMPTS = 5
OTP_LOCKOUT_MINUTES = 15
OTP_RESEND_SECONDS = 60


def generate_otp():
    return f'{secrets.randbelow(1_000_000):06d}'


def send_otp_email(user, otp):
    subject = 'Seu código de acesso — Inno Book'
    ctx = {'otp': otp, 'user': user, 'validity': OTP_VALID_MINUTES}
    html = render_to_string('emails/otp_email.html', ctx)
    plain = render_to_string('emails/otp_email.txt', ctx)
    send_mail(
        subject,
        plain,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html,
        fail_silently=False,
    )


def send_verification_email(request, user):
    from django.contrib.auth.tokens import default_token_generator
    from django.urls import reverse
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    url = request.build_absolute_uri(
        reverse('accounts:verify_email', args=[uidb64, token])
    )

    subject = 'Confirme seu e-mail — Inno Book'
    html = render_to_string(
        'emails/verify_email.html', {'url': url, 'user': user}
    )
    plain = render_to_string('emails/verify_email.txt', {'url': url, 'user': user})
    send_mail(
        subject,
        plain,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html,
        fail_silently=False,
    )


def requires_two_factor(user):
    return bool(user.two_factor_enabled or user.is_producer() or user.is_staff)


def start_two_factor_login(request, user):
    """Inicia o fluxo de OTP antes de logar (login do site)."""
    otp = generate_otp()
    request.session['otp_user_id'] = user.pk
    request.session['otp_code'] = otp
    request.session['otp_expires'] = (
        timezone.now() + timedelta(minutes=OTP_VALID_MINUTES)
    ).isoformat()
    request.session.pop('otp_attempts', None)
    request.session.pop('otp_locked_until', None)
    mark_otp_sent(request)
    send_otp_email(user, otp)


def send_fresh_otp(request, user):
    """Reenvia um novo OTP para um usuário já autenticado (ex.: admin)."""
    otp = generate_otp()
    request.session['otp_code'] = otp
    request.session['otp_expires'] = (
        timezone.now() + timedelta(minutes=OTP_VALID_MINUTES)
    ).isoformat()
    mark_otp_sent(request)
    send_otp_email(user, otp)

def verify_otp(request, code):
    stored = request.session.get('otp_code')
    if not stored:
        return False
    expires = request.session.get('otp_expires')
    if not expires or timezone.now() > timezone.datetime.fromisoformat(expires):
        request.session.pop('otp_code', None)
        request.session.pop('otp_expires', None)
        return False
    if secrets.compare_digest(stored, str(code)):
        request.session.pop('otp_code', None)
        request.session.pop('otp_expires', None)
        request.session.pop('otp_attempts', None)
        request.session.pop('otp_locked_until', None)
        return True
    return False


def otp_is_locked(request):
    """True se o código 2FA atual estiver bloqueado por excesso de erros."""
    locked_until = request.session.get('otp_locked_until')
    if not locked_until:
        return False
    if timezone.now() < timezone.datetime.fromisoformat(locked_until):
        return True
    request.session.pop('otp_locked_until', None)
    request.session.pop('otp_attempts', None)
    return False


def record_otp_failure(request):
    """Conta erro de OTP; após MAX_OTP_ATTEMPTS bloqueia e invalida o código."""
    attempts = request.session.get('otp_attempts', 0) + 1
    request.session['otp_attempts'] = attempts
    if attempts >= MAX_OTP_ATTEMPTS:
        request.session['otp_locked_until'] = (
            timezone.now() + timedelta(minutes=OTP_LOCKOUT_MINUTES)
        ).isoformat()
        request.session.pop('otp_code', None)
        request.session.pop('otp_expires', None)


def otp_can_resend(request):
    """Respeita cooldown de reenvio do código (evita bombardeio de e-mail)."""
    last_sent = request.session.get('otp_sent_at')
    if not last_sent:
        return True
    elapsed = timezone.now() - timezone.datetime.fromisoformat(last_sent)
    return elapsed.total_seconds() >= OTP_RESEND_SECONDS


def mark_otp_sent(request):
    request.session['otp_sent_at'] = timezone.now().isoformat()


def record_login_failure(user):
    user.failed_login_count += 1
    if user.failed_login_count >= MAX_LOGIN_ATTEMPTS:
        user.locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
        user.failed_login_count = 0
    user.save(update_fields=['failed_login_count', 'locked_until'])


def reset_login_failures(user):
    if user.failed_login_count or user.locked_until:
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=['failed_login_count', 'locked_until'])
