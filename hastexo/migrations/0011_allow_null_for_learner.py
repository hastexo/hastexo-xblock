from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hastexo', '0010_add_user_foreign_key'),
    ]

    # Because 0010_add_user_foreign_key was buggy in several releases,
    # and those set the field to be NOT NULL, what we have to do here
    # is undo that. For an installation that undergoes both
    # 0010_add_user_foreign_key and this migration in a fixed release,
    # this AlterField will be a no-op. For one that ran
    # 0010_add_user_foreign_key from a broken release and thus had its
    # field set to NOT NULL, this will allow NULL values.
    operations = [
        migrations.AlterField(
            model_name='stack',
            name='learner',
            field=models.ForeignKey(
                db_constraint=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL),
        ),
    ]
