from django.db import migrations


FIELDS = [
    ('Ebook',      ['file', 'file_epub', 'file_mobi']),
    ('EbookBonus', ['file', 'file_epub', 'file_mobi']),
]


def remover_prefixo_protected(apps, schema_editor):
    """Ajusta os nomes salvos no banco: 'protected/ebooks/x' -> 'ebooks/x'."""
    for model_name, field_names in FIELDS:
        Model = apps.get_model('products', model_name)
        for obj in Model.objects.all():
            changed = False
            for f in field_names:
                value = getattr(obj, f)
                name = value.name if hasattr(value, 'name') else value
                if name and name.startswith('protected/'):
                    setattr(obj, f, name[len('protected/'):])
                    changed = True
            if changed:
                obj.save()


def readicionar_prefixo_protected(apps, schema_editor):
    for model_name, field_names in FIELDS:
        Model = apps.get_model('products', model_name)
        for obj in Model.objects.all():
            changed = False
            for f in field_names:
                value = getattr(obj, f)
                name = value.name if hasattr(value, 'name') else value
                if name and not name.startswith('protected/'):
                    setattr(obj, f, 'protected/' + name)
                    changed = True
            if changed:
                obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_alter_ebook_file_alter_ebook_file_epub_and_more'),
    ]

    operations = [
        migrations.RunPython(remover_prefixo_protected, readicionar_prefixo_protected),
    ]
