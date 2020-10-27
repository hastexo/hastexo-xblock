from __future__ import print_function

import sys

from django.db import transaction, close_old_connections
from django.utils import timezone

from .models import Stack
from .provider import Provider
from .tasks import DeleteStackTask, SuspendStackTask
from .common import (
    UP_STATES,
    SUSPEND_PENDING,
    SUSPEND_RETRY,
    SUSPEND_FAILED,
    DELETE_COMPLETE,
    DELETE_IN_PROGRESS,
    DELETE_PENDING,
    LAUNCH_PENDING,
    CREATE_COMPLETE
)


class AbstractJob(object):
    """
    Parent job class.

    """
    settings = {}

    def __init__(self, settings):
        self.settings = settings

    def log(self, msg):
        """
        Log message to stdout.

        """
        print(msg, file=sys.stderr)

    def refresh_db(self):
        """
        Destroy old or unusable database connections.  Django will reconnect as
        needed.

        """
        close_old_connections()


class SuspenderJob(AbstractJob):
    """
    Suspends stacks.

    """
    def run(self):
        timeout = self.settings.get("suspend_timeout", 120)
        concurrency = self.settings.get("suspend_concurrency", 4)
        timedelta = timezone.timedelta(seconds=timeout)
        cutoff = timezone.now() - timedelta

        # SUSPEND_RETRY is no longer needed: we always retry on a suspend
        # failure.  It is, thus, deprecated.
        states = list(UP_STATES) + [SUSPEND_RETRY, SUSPEND_FAILED]

        self.refresh_db()

        # Get stacks to suspend
        with transaction.atomic():
            stacks = Stack.objects.select_for_update().filter(
                suspend_timestamp__isnull=False
            ).filter(
                suspend_timestamp__lt=cutoff
            ).filter(
                status__in=states
            ).exclude(
                provider__exact=''
            ).order_by('suspend_timestamp')[:concurrency]

            for stack in stacks:
                stack.status = SUSPEND_PENDING
                stack.save(update_fields=["status"])

        # Suspend them
        for stack in stacks:
            self.suspend_stack(stack)

    def suspend_stack(self, stack):
        """
        Start an asynchronous suspend task with no expiration and ignoring
        results.

        """
        soft_time_limit = self.settings.get("suspend_task_timeout", 900)
        hard_time_limit = soft_time_limit + 30
        kwargs = {
            "stack_id": stack.id
        }
        SuspendStackTask().apply_async(
            kwargs=kwargs,
            soft_time_limit=soft_time_limit,
            time_limit=hard_time_limit,
            ignore_result=True
        )


class ReaperJob(AbstractJob):
    """
    Deletes old stacks.

    """
    def run(self):
        dont_delete = [DELETE_PENDING,
                       DELETE_COMPLETE,
                       DELETE_IN_PROGRESS,
                       LAUNCH_PENDING,
                       CREATE_COMPLETE]

        self.refresh_db()

        # Get stacks to delete
        with transaction.atomic():
            stacks = Stack.objects.select_for_update().filter(
                suspend_timestamp__isnull=False
            ).filter(
                delete_by__isnull=False
            ).filter(
                delete_by__lt=timezone.now()
            ).exclude(
                status__in=dont_delete
            ).exclude(
                provider__exact=''
            ).order_by('suspend_timestamp')

            for stack in stacks:
                stack.status = DELETE_PENDING
                stack.save(update_fields=["status"])

        # Delete them
        for stack in stacks:
            self.delete_stack(stack)

        # Apocalypse pass: kill all zombie stacks
        providers = self.settings.get("providers", {})
        for provider_name in providers:
            provider = Provider.init(provider_name)
            try:
                provider_stacks = provider.get_stacks()
            except Exception as e:
                error_msg = "Error listing stacks for provider [%s]: %s" % (
                    provider_name, str(e))
                self.log(error_msg)
                continue

            for provider_stack in provider_stacks:
                stack_name = provider_stack["name"]

                try:
                    stack = Stack.objects.get(name=stack_name)
                except Stack.DoesNotExist:
                    continue

                if stack.status == DELETE_COMPLETE:
                    error_msg = ("Zombie stack [%s] detected at provider [%s]"
                                 % (stack_name, provider_name))
                    self.log(error_msg)
                    stack.provider = provider_name
                    stack.status = DELETE_PENDING
                    stack.error_msg = error_msg
                    stack.save(update_fields=[
                        "provider",
                        "status",
                        "error_msg"
                    ])

                    self.delete_stack(stack)

    def delete_stack(self, stack):
        """
        Start an asynchronous delete task with no expiration and ignoring
        results.

        """
        soft_time_limit = self.settings.get("delete_task_timeout", 900)
        hard_time_limit = soft_time_limit + 30
        kwargs = {
            "stack_id": stack.id
        }
        DeleteStackTask().apply_async(
            kwargs=kwargs,
            soft_time_limit=soft_time_limit,
            time_limit=hard_time_limit,
            ignore_result=True
        )
