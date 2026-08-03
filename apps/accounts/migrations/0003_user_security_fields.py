import apps.accounts.validators
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_user_cpf'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_verified',
            field=models.BooleanField(default=False, verbose_name='E-mail verificado'),
        ),
        migrations.AddField(
            model_name='user',
            name='failed_login_count',
            field=models.PositiveIntegerField(default=0, verbose_name='Tentativas de login falhas'),
        ),
        migrations.AddField(
            model_name='user',
            name='locked_until',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Bloqueado até'),
        ),
        migrations.AddField(
            model_name='user',
            name='producer_approved',
            field=models.BooleanField(default=False, verbose_name='Produtor aprovado'),
        ),
        migrations.AddField(
            model_name='user',
            name='producer_requested',
            field=models.BooleanField(default=False, verbose_name='Solicitou ser produtor'),
        ),
        migrations.AddField(
            model_name='user',
            name='two_factor_enabled',
            field=models.BooleanField(default=False, verbose_name='2FA ativo'),
        ),
        migrations.AlterField(
            model_name='user',
            name='cpf',
            field=models.CharField(
                max_length=14,
                blank=True,
                null=True,
                validators=[apps.accounts.validators.validar_cpf],
                verbose_name='CPF',
            ),
        ),
    ]
