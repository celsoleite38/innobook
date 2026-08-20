from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

# Extensões permitidas por tipo de arquivo
FORMATOS_EBOOK   = ['pdf', 'epub', 'mobi']
FORMATOS_IMAGEM  = ['jpg', 'jpeg', 'png', 'webp', 'gif']
FORMATOS_PREVIEW = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'gif']


def _get_limite(tipo='ebook'):
    """
    Busca o limite configurado no admin.
    Fallback para valores fixos se o banco não estiver disponível.
    """
    try:
        from apps.payments.models import PlatformConfig
        config = PlatformConfig.get()
        mapa = {
            'ebook'  : config.max_upload_size_mb,
            'capa'   : config.max_cover_size_mb,
            'preview': config.max_preview_size_mb,
        }
        return mapa.get(tipo, 5) * 1024 * 1024
    except Exception:
        return 5 * 1024 * 1024  # fallback 5MB


def validar_tamanho(upload, tipo='ebook'):
    """Rejeita uploads acima do limite configurado no admin."""
    if not upload:
        return
    try:
        limite    = _get_limite(tipo)
        limite_mb = limite // (1024 * 1024)
        if upload.size > limite:
            raise ValidationError(
                f'O arquivo excede o limite de {limite_mb} MB. '
                'Escolha um arquivo menor.'
            )
    except ValidationError:
        raise
    except (FileNotFoundError, OSError):
        return


def validar_ebook(upload):
    """Valida arquivos de eBook (pdf/epub/mobi) e o tamanho."""
    if not upload:
        return
    FileExtensionValidator(
        FORMATOS_EBOOK,
        'Formato não permitido. Use PDF, EPUB ou MOBI.'
    )(upload)
    validar_tamanho(upload, tipo='ebook')


def validar_imagem(upload):
    """Valida capas (imagens) e o tamanho."""
    if not upload:
        return
    FileExtensionValidator(
        FORMATOS_IMAGEM,
        'Formato não permitido. Use JPG, PNG, WEBP ou GIF.'
    )(upload)
    validar_tamanho(upload, tipo='capa')


def validar_preview(upload):
    """Valida preview — aceita PDF e imagens."""
    if not upload:
        return
    FileExtensionValidator(
        FORMATOS_PREVIEW,
        'Formato não permitido. Use PDF, JPG, PNG, WEBP ou GIF.'
    )(upload)
    validar_tamanho(upload, tipo='preview')