from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator


# Limite de upload (combinado com o validar_tamanho.js no cliente)
MAX_UPLOAD_SIZE = 3 * 1024 * 1024  # 3 MB

# Extensões permitidas por tipo de arquivo
FORMATOS_EBOOK = ['pdf', 'epub', 'mobi']
FORMATOS_IMAGEM = ['jpg', 'jpeg', 'png', 'webp', 'gif']

TAMANHO = (
    f'O arquivo excede o limite de {MAX_UPLOAD_SIZE // (1024 * 1024)} MB. '
    'Escolha um arquivo menor.'
)


def validar_tamanho(upload):
    """Rejeita uploads acima de MAX_UPLOAD_SIZE."""
    if upload and upload.size > MAX_UPLOAD_SIZE:
        raise ValidationError(TAMANHO)


def validar_ebook(upload):
    """Valida arquivos de eBook (pdf/epub/mobi) e o tamanho."""
    if not upload:
        return
    FileExtensionValidator(FORMATOS_EBOOK, 'Formato não permitido. Use PDF, EPUB ou MOBI.')(upload)
    validar_tamanho(upload)


def validar_imagem(upload):
    """Valida capas/preview (imagens) e o tamanho."""
    if not upload:
        return
    FileExtensionValidator(FORMATOS_IMAGEM, 'Formato não permitido. Use JPG, PNG, WEBP ou GIF.')(upload)
    validar_tamanho(upload)
