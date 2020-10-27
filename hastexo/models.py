from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone
from jsonfield.fields import JSONField

SETTINGS_KEY = 'hastexo'
DEFAULT_SETTINGS = {"delete_age": 14}


def default_delete_by_timestamp():
    # load the default delete_age value from settings
    try:
        settings = django_settings.XBLOCK_SETTINGS.get(
            SETTINGS_KEY,
            DEFAULT_SETTINGS
        )
    except AttributeError:
        settings = DEFAULT_SETTINGS

    # create a delete_by timestamp based on the delete_age from settings
    delete_by = timezone.now() + timezone.timedelta(
        days=settings.get("delete_age", 14))

    return delete_by


class StackCommon(models.Model):
    """
    Abstract class that defines a stack record's common fields.

    """
    class Meta:
        abstract = True

    name = models.CharField(max_length=64, db_index=True)
    student_id = models.CharField(max_length=40, db_index=True)
    course_id = models.CharField(max_length=50, db_index=True)
    run = models.CharField(max_length=50, blank=True)
    provider = models.CharField(max_length=32, blank=True)
    providers = JSONField(default=list)
    hook_script = models.CharField(max_length=256, null=True)
    hook_events = JSONField(default=dict)
    protocol = models.CharField(max_length=32, blank=True)
    port = models.IntegerField(null=True)
    status = models.CharField(max_length=32, blank=True, db_index=True)
    error_msg = models.CharField(max_length=256, blank=True)
    ip = models.GenericIPAddressField(null=True)
    user = models.CharField(max_length=32, blank=True)
    launch_task_id = models.CharField(max_length=40, blank=True)
    launch_timestamp = models.DateTimeField(null=True, db_index=True)
    suspend_timestamp = models.DateTimeField(null=True, db_index=True)
    created_on = models.DateTimeField(auto_now_add=True, db_index=True)
    delete_age = models.IntegerField(null=True)
    delete_by = models.DateTimeField(null=True, db_index=True,
                                     default=default_delete_by_timestamp)


class Stack(StackCommon):
    """
    Stores Heat stack data that needs to be queried across XBlock instances.

    """
    class Meta:
        app_label = 'hastexo'
        unique_together = (('student_id', 'course_id', 'name'),)

    key = models.TextField(blank=True)
    password = models.CharField(max_length=128, blank=True)

    def __init__(self, *args, **kwargs):
        super(Stack, self).__init__(*args, **kwargs)

        # Save previous status
        self.prev_status = self.status

    def save(self, *args, **kwargs):
        super(Stack, self).save(*args, **kwargs)

        # Populate the log if there was a status change
        if self.status and self.status != self.prev_status:
            self.prev_status = self.status

            log_fields = {'stack_id': self.id}
            for field in StackCommon._meta.get_fields():
                if field.name == 'created_on':
                    continue
                log_fields[field.name] = getattr(self, field.name)

            log = StackLog(**log_fields)
            log.save()


class StackLog(StackCommon):
    """
    A log of stack model changes.

    """
    class Meta:
        app_label = 'hastexo'

    stack_id = models.IntegerField(null=True, db_index=True)
