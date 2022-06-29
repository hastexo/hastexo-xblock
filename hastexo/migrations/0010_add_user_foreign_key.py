from django.conf import settings
from django.db import migrations, models, OperationalError
import django.db.models.deletion


class Migration(migrations.Migration):

    def check_stacks(apps, schema_editor):
        """
        Check if all stacks can be linked to a real user account.
        If not, error out with a suggestion how to proceed.
        """
        Stack = apps.get_model("hastexo", "Stack")
        AnonymousUserId = apps.get_model("student", "AnonymousUserId")
        anonymous_user_ids = AnonymousUserId.objects.values(
            'anonymous_user_id').distinct()
        problematic_stacks = Stack.objects.exclude(
            student_id__in=anonymous_user_ids)

        if len(problematic_stacks) > 0:
            raise OperationalError(
                'Unable to link stacks to users; please make sure that '
                'the following stacks have a student_id that corresponds '
                'to a real user account: '
                f'{[s.name for s in problematic_stacks]}. '
                'Please update or delete the stacks manually and rerun '
                'the migration.')

    def backfill_learner(apps, schema_editor):
        """
        Use the 'student_id' to link stacks to the User model.
        """
        Stack = apps.get_model("hastexo", "Stack")
        AnonymousUserId = apps.get_model("student", "AnonymousUserId")
        for stack in Stack.objects.all():
            stack.learner = AnonymousUserId.objects.get(
                anonymous_user_id=stack.student_id).user
            stack.save(update_fields=['learner'])

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hastexo', '0009_add_null_true_for_key_and_password'),
    ]

    operations = [
        migrations.RunPython(check_stacks),
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
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL),
        ),
    ]
