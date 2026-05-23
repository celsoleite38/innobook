from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from .models import DownloadToken, DownloadLog
from .utils import get_client_ip
import os


@login_required
def download_ebook(request, token):
    """
    Serve o PDF protegido sem expor a URL real do arquivo.
    Valida token, limite de downloads e expiração.
    """

    dt = get_object_or_404(DownloadToken, token=token)

    # Verifica se o token pertence ao usuário logado
    if dt.order.buyer != request.user:
        return HttpResponseForbidden('Acesso negado.')

    # Valida o token
    if not dt.is_valid:
        if dt.is_expired:
            return HttpResponseForbidden('Link expirado.')
        if dt.is_limit_reached:
            return HttpResponseForbidden('Limite de downloads atingido.')
        return HttpResponseForbidden('Token inválido.')

    # Registra o download
    ip = get_client_ip(request)
    dt.register_download(ip=ip)

    # Log detalhado
    DownloadLog.objects.create(
        token      = dt,
        ip_address = ip,
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500],
    )

    # Serve o arquivo sem expor o caminho real
    file_path = dt.order.ebook.file.path

    if not os.path.exists(file_path):
        return HttpResponseForbidden('Arquivo não encontrado.')

    filename = f"{dt.order.ebook.title}.pdf"
    response = FileResponse(
        open(file_path, 'rb'),
        content_type='application/pdf'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response