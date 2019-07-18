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
                self.log("Cannot suspend stack [%s] with status [%s]." %
                         (stack.name, provider_stack["status"]))

                # Schedule for retry, if it makes sense to do so
                if (provider_stack["status"] != DELETED_STATE and
                        'FAILED' not in provider_stack["status"]):
                    stack.status = SUSPEND_RETRY_STATE
                else:
                    stack.status = provider_stack["status"]

                stack.save(update_fields=["status"])
        except Exception as e:
            # Schedule for retry on any uncaught exception
            stack.status = SUSPEND_RETRY_STATE
            stack.save(update_fields=["status"])
            self.log("Error suspending stack [%s]: %s" % (stack.name, str(e)))


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
                # Roll stack status back
                stack.status = prev_states[i]
                stack.save(update_fields=["status"])
                self.log("Error deleting stack [%s]: %s" % (
                    stack.name, str(e)))

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
                self.log("Stack [%s] deletion failed." % stack.name)
                stack.status = DELETE_FAILED_STATE
                stack.save(update_fields=["status"])
            elif stack.status != DELETE_IN_PROGRESS_STATE:
                attempt += 1

                if attempt > attempts:
                    self.log("Stack [%s] deletion retries exceeded." %
                             stack.name)
                    stack.status = DELETE_FAILED_STATE
                else:
                    self.log("Deleting stack [%s]." % (stack.name))
                    provider.delete_stack(stack.name, False)
                    stack.status = DELETE_IN_PROGRESS_STATE

                stack.save(update_fields=["status"])
