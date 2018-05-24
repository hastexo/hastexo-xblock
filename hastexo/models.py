from django.db import models


class StackCommon(models.Model):
    """
    Abstract class that defines a stack record's common fields.

    """
    class Meta:
        app_label = 'hastexo'
        abstract = True

    name = models.CharField(max_length=64, db_index=True)
    student_id = models.CharField(max_length=40, db_index=True)
    course_id = models.CharField(max_length=50, db_index=True)
    provider = models.CharField(max_length=32, blank=True)
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


class Stack(StackCommon):
    """
    Stores Heat stack data that needs to be queried across XBlock instances.

    """
    class Meta:
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
            log_fields = {'stack': self}
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

    stack = models.ForeignKey('Stack', null=True, on_delete=models.SET_NULL)
