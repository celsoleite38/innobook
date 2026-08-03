from django.db import migrations

from apps.accounts.validators import cpf_somente_digitos, cpf_valido


def limpar_cpfs_invalidos(apps, schema_editor):
    """Remove CPFs placeholder/inválidos para permitir a constraint UNIQUE."""
    User = apps.get_model('accounts', 'User')
    for user in User.objects.exclude(cpf__isnull=True).exclude(cpf=''):
        cpf = cpf_somente_digitos(user.cpf)
        if not cpf_valido(cpf):
            user.cpf = None
            user.save(update_fields=['cpf'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_security_fields'),
    ]

    operations = [
        migrations.RunPython(limpar_cpfs_invalidos, migrations.RunPython.noop),
    ]
