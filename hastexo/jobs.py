from __future__ import print_function

import time
import sys

from django.db import transaction, close_old_connections
from django.utils import timezone
from multiprocessing.dummy import Pool as ThreadPool

from .models import Stack
from .provider import Provider
from .common import (UP_STATES, LAUNCH_STATE, SUSPEND_STATE,
                     SUSPEND_ISSUED_STATE, SUSPEND_RETRY_STATE,
                     SUSPEND_FAILED_STATE, DELETED_STATE,
                     DELETE_IN_PROGRESS_STATE, DELETE_FAILED_STATE,
                     DELETE_STATE)


class AbstractJob(object):
    """
    Suspends stacks.

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
        states = list(UP_STATES) + [LAUNCH_STATE,
                                    SUSPEND_RETRY_STATE,
                                    SUSPEND_FAILED_STATE]

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
                stack.status = SUSPEND_STATE
                stack.save(update_fields=["status"])

        # Suspend them
        if self.settings.get("suspend_in_parallel", True):
            pool = ThreadPool(concurrency)
            pool.map(self.suspend_stack, stacks)
            pool.close()
            pool.join()
        else:
            for stack in stacks:
                self.suspend_stack(stack)

    def suspend_stack(self, stack):
        """
        Suspend the stack.

        """
        try:
            provider = Provider.init(stack.provider)
            provider_stack = provider.get_stack(stack.name)

            if provider_stack["status"] in UP_STATES + (SUSPEND_FAILED_STATE,):
                self.log("Suspending stack [%s]." % stack.name)

                # Suspend stack
                provider.suspend_stack(stack.name)

                # Save status
                stack.status = SUSPEND_ISSUED_STATE
                stack.save(update_fields=["status"])
            else:
                error_msg = "Cannot suspend stack [%s] with status [%s]." % (
                    stack.name, provider_stack["status"])
                self.log(error_msg)
                stack.error_msg = error_msg

                # Schedule for retry, if it makes sense to do so
                if (provider_stack["status"] != DELETED_STATE and
                        'FAILED' not in provider_stack["status"]):
                    stack.status = SUSPEND_RETRY_STATE
                else:
                    stack.status = provider_stack["status"]

                stack.save(update_fields=["status", "error_msg"])
        except Exception as e:
            error_msg = "Error suspending stack [%s]: %s" % (
                stack.name, str(e))
            self.log(error_msg)
            stack.error_msg = error_msg

            # Schedule for retry on any uncaught exception
            stack.status = SUSPEND_RETRY_STATE
            stack.save(update_fields=["status", "error_msg"])


class ReaperJob(AbstractJob):
    """
    Deletes old stacks.

    """
    def run(self):
        age = self.settings.get("delete_age", 14)
        if not age:
            return

        attempts = self.settings.get("delete_attempts", 3)
        if not attempts:
            return

        timedelta = timezone.timedelta(days=age)
        cutoff = timezone.now() - timedelta
        dont_delete = [DELETE_STATE,
                       DELETED_STATE,
                       DELETE_IN_PROGRESS_STATE]

        self.refresh_db()

        # Get stacks to delete
        with transaction.atomic():
            stacks = Stack.objects.select_for_update().filter(
                suspend_timestamp__isnull=False
            ).filter(
                suspend_timestamp__lt=cutoff
            ).exclude(
                status__in=dont_delete
            ).exclude(
                provider__exact=''
            ).order_by('suspend_timestamp')

            prev_states = []
            for stack in stacks:
                prev_states.append(stack.status)
                stack.status = DELETE_STATE
                stack.save(update_fields=["status"])

        # Delete them
        for i, stack in enumerate(stacks):
            try:
                self.delete_stack(stack)
            except Exception as e:
                error_msg = "Error deleting stack [%s]: %s" % (
                    stack.name, str(e))
                self.log(error_msg)
                stack.error_msg = error_msg

                # Roll stack status back
                stack.status = prev_states[i]
                stack.save(update_fields=["status", "error_msg"])

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

                if stack.status == DELETED_STATE:
                    error_msg = ("Zombie stack [%s] detected at provider [%s]"
                                 % (stack_name, provider_name))
                    self.log(error_msg)
                    stack.provider = provider_name
                    stack.status = DELETE_STATE
                    stack.error_msg = error_msg
                    stack.save(update_fields=[
                        "provider",
                        "status",
                        "error_msg"
                    ])

                    try:
                        self.delete_stack(stack)
                    except Exception as e:
                        error_msg = "Error deleting zombie stack [%s]: %s" % (
                            stack.name, str(e))
                        self.log(error_msg)
                        stack.status = DELETE_FAILED_STATE
                        stack.error_msg = error_msg
                        stack.save(update_fields=["status", "error_msg"])

    def delete_stack(self, stack):
        """
        Delete the stack.

        """
        timeouts = self.settings.get('task_timeouts', {})
        sleep = timeouts.get('sleep', 10)
        retries = timeouts.get('retries', 90)
        attempts = self.settings.get('delete_attempts', 3)
        provider = Provider.init(stack.provider)

        def update_stack_status():
            provider_stack = provider.get_stack(stack.name)
            stack.status = provider_stack["status"]
            stack.save(update_fields=["status"])

        update_stack_status()
        retry = 0
        attempt = 0
        while (stack.status != DELETED_STATE and
               retry < retries and
               attempt <= attempts):

            if retry:
                time.sleep(sleep)
                update_stack_status()

            retry += 1

            if stack.status == DELETED_STATE:
                self.log("Stack [%s] deleted successfully." % stack.name)
            elif retry >= retries:
                error_msg = "Stack [%s] deletion attempt [%d] failed." % (
                    stack.name, attempt)
                self.log(error_msg)
                stack.error_msg = error_msg
                stack.status = DELETE_FAILED_STATE
                stack.save(update_fields=["status", "error_msg"])
            elif stack.status != DELETE_IN_PROGRESS_STATE:
                attempt += 1

                if attempt > attempts:
                    error_msg = ("Stack [%s] deletion retries exceeded after "
                                 "[%d] attempts." % (stack.name, attempts))
                    self.log(error_msg)
                    stack.error_msg = error_msg
                    stack.status = DELETE_FAILED_STATE
                    stack.save(update_fields=["status", "error_msg"])
                else:
                    self.log("Attempt [%d] to delete stack [%s]." % (
                        attempt, stack.name))
                    provider.delete_stack(stack.name, False)
                    stack.status = DELETE_IN_PROGRESS_STATE
                    stack.save(update_fields=["status"])
