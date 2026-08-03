from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ProtectedFileSystemStorage(FileSystemStorage):
    """
    Armazena arquivos protegidos (eBooks/bônus) FORA do diretório público
    de mídia (MEDIA_ROOT). Esses arquivos nunca possuem URL pública — só são
    entregues pela view autenticada de download (via token).
    """

    def __init__(self):
        super().__init__(location=settings.PROTECTED_ROOT, base_url=None)

    def url(self, name):
        raise ValueError('Arquivos protegidos não possuem URL pública.')
