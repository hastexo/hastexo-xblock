from django.contrib.auth.models import User
from django.db import models


class AnonymousUserId(models.Model):
    """
    Pared down from:

    edx-platform/common/djangoapps/student/models.py:AnonymousUserId

    This is so we don't have to install all of edx-platform just to test it.

    """
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)
    anonymous_user_id = models.CharField(unique=True, max_length=32)
