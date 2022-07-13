from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import migrations, models
import django.db.models.deletion

import logging
logger = logging.getLogger(__name__)


class Migration(migrations.Migration):

    def backfill_learner(apps, schema_editor):
        """
        Use the 'student_id' to link stacks to the User model.
        """
        Stack = apps.get_model("hastexo", "Stack")
        AnonymousUserId = apps.get_model("student", "AnonymousUserId")
        for stack in Stack.objects.all():
            try:
                stack.learner = AnonymousUserId.objects.get(
                    anonymous_user_id=stack.student_id).user
                stack.save(update_fields=['learner'])
            except ObjectDoesNotExist:
                logger.warning('Unable to link stack to user: '
                               f'{stack.name}')

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hastexo', '0009_add_null_true_for_key_and_password'),
    ]

    operations = [
        migrations.AddField(
            model_name='stack',
            name='learner',
            field=models.ForeignKey(
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_learner),
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
