from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from .models import DownloadToken, DownloadLog
from .utils import get_client_ip
import os


@login_required
def download_ebook(request, token):
    dt = get_object_or_404(DownloadToken, token=token)

    if dt.order.buyer != request.user:
        return HttpResponseForbidden('Acesso negado.')

    if not dt.is_valid:
        if dt.is_expired:
            return HttpResponseForbidden('Link expirado.')
        if dt.is_limit_reached:
            return HttpResponseForbidden('Limite de downloads atingido.')
        return HttpResponseForbidden('Token inválido.')

    # Formato solicitado (pdf, epub, mobi) — padrão PDF
    fmt = request.GET.get('format', 'pdf').lower()

    ebook = dt.order.ebook

    if fmt == 'epub' and ebook.file_epub:
        file_path    = ebook.file_epub.path
        content_type = 'application/epub+zip'
        extension    = 'epub'
    elif fmt == 'mobi' and ebook.file_mobi:
        file_path    = ebook.file_mobi.path
        content_type = 'application/x-mobipocket-ebook'
        extension    = 'mobi'
    else:
        file_path    = ebook.file.path
        content_type = 'application/pdf'
        extension    = 'pdf'

    if not os.path.exists(file_path):
        return HttpResponseForbidden('Arquivo não encontrado.')

    ip = get_client_ip(request)
    dt.register_download(ip=ip)

    DownloadLog.objects.create(
        token      = dt,
        ip_address = ip,
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500],
    )

    filename = f"{ebook.title}.{extension}"
    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_bonus(request, token, bonus_id):
    """Download de eBook bônus vinculado a um pedido pago."""
    from apps.products.models import EbookBonus

    dt = get_object_or_404(DownloadToken, token=token)

    if dt.order.buyer != request.user:
        return HttpResponseForbidden('Acesso negado.')

    if not dt.is_valid:
        return HttpResponseForbidden('Token inválido ou expirado.')

    bonus = get_object_or_404(EbookBonus, pk=bonus_id, ebook=dt.order.ebook)

    fmt = request.GET.get('format', 'pdf').lower()

    if fmt == 'epub' and bonus.file_epub:
        file_path    = bonus.file_epub.path
        content_type = 'application/epub+zip'
        extension    = 'epub'
    elif fmt == 'mobi' and bonus.file_mobi:
        file_path    = bonus.file_mobi.path
        content_type = 'application/x-mobipocket-ebook'
        extension    = 'mobi'
    elif bonus.file:
        file_path    = bonus.file.path
        content_type = 'application/pdf'
        extension    = 'pdf'
    else:
        return HttpResponseForbidden('Arquivo não disponível.')

    if not os.path.exists(file_path):
        return HttpResponseForbidden('Arquivo não encontrado.')

    filename = f"{bonus.title}.{extension}"
    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response