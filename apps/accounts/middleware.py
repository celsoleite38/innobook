from django.shortcuts import redirect
from django.urls import reverse

from .security import requires_two_factor

EXEMPT_PATHS = (
    '/admin/login/',
    '/admin/logout/',
    '/admin/password_change/',
    '/accounts/login/',
    '/accounts/logout/',
    '/accounts/2fa/',
    '/accounts/verify-email/',
    '/static/',
    '/media/',
)


class TwoFactorVerificationMiddleware:
    """
    Garante que usuários que exigem 2FA (produtores, staff ou quem habilitou)
    tenham a sessão marcada como verificada antes de acessar qualquer página —
    incluindo o Django admin.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            user.is_authenticated
            and requires_two_factor(user)
            and not request.session.get('two_factor_verified')
        ):
            if not request.path_info.startswith(EXEMPT_PATHS):
                return redirect(
                    reverse('accounts:two_factor') + '?next=' + request.path_info
                )
        return self.get_response(request)
