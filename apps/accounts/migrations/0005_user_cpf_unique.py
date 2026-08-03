import apps.accounts.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_limpar_cpfs_invalidos'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='cpf',
            field=models.CharField(
                max_length=14,
                unique=True,
                blank=True,
                null=True,
                validators=[apps.accounts.validators.validar_cpf],
                verbose_name='CPF',
            ),
        ),
    ]
