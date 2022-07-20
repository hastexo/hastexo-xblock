from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hastexo', '0011_allow_null_for_learner'),
    ]

    operations = [
        migrations.AddField(
            model_name='stack',
            name='suspend_by',
            field=models.DateTimeField(db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='stacklog',
            name='suspend_by',
            field=models.DateTimeField(db_index=True, null=True),
        ),
    ]
