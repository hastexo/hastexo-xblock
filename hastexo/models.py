from django.db import models


class StackCommon(models.Model):
    """
    Abstract class that defines a stack record's common fields.

    """
    class Meta:
        abstract = True

    name = models.CharField(max_length=64, db_index=True)
    student_id = models.CharField(max_length=40, db_index=True)
    course_id = models.CharField(max_length=50, db_index=True)
    provider = models.CharField(max_length=32)
    protocol = models.CharField(max_length=32)
    port = models.IntegerField(null=True)
    status = models.CharField(max_length=32, db_index=True)
    error_msg = models.CharField(max_length=256)
    ip = models.GenericIPAddressField(null=True)
    user = models.CharField(max_length=32)
    launch_task_id = models.CharField(max_length=40)
    launch_timestamp = models.DateTimeField(null=True, db_index=True)
    suspend_timestamp = models.DateTimeField(null=True, db_index=True)
    created_on = models.DateTimeField(auto_now_add=True, db_index=True)


class Stack(StackCommon):
    """
    Stores Heat stack data that needs to be queried across XBlock instances.

    """
    class Meta:
        unique_together = (('student_id', 'course_id', 'name'),)

    key = models.TextField()
    password = models.CharField(max_length=128)

    def save(self, *args, **kwargs):
        super(Stack, self).save(*args, **kwargs)

        # Populate the log
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
