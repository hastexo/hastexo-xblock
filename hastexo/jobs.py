from django.db import transaction
from django.utils import timezone
from heatclient.exc import HTTPNotFound
from multiprocessing.dummy import Pool as ThreadPool

from .heat import HeatWrapper
from .models import Stack
from .utils import (UP_STATES, LAUNCH_STATE, SUSPEND_STATE,
                    SUSPEND_ISSUED_STATE, SUSPEND_RETRY_STATE, DELETE_STATE,
                    get_xblock_configuration)


class SuspenderJob(object):
    """
    Suspends stacks.

    """
    settings = {}
    stdout = None

    def __init__(self, settings, stdout):
        self.settings = settings
        self.stdout = stdout

    def run(self):
        """
        Suspend stacks.

        """
        timeout = self.settings.get("suspend_timeout", 120)
        concurrency = self.settings.get("suspend_concurrency", 4)
        timedelta = timezone.timedelta(seconds=timeout)
        cutoff = timezone.now() - timedelta
        states = list(UP_STATES) + [LAUNCH_STATE, SUSPEND_RETRY_STATE]

        # Get stacks to suspend
        with transaction.atomic():
            stacks = Stack.objects.select_for_update().filter(
                suspend_timestamp__isnull=False
            ).filter(
                suspend_timestamp__lt=cutoff
            ).filter(
                status__in=states
            ).order_by('suspend_timestamp')[:concurrency]

            for stack in stacks:
                stack.status = SUSPEND_STATE
                stack.save()

        # Suspend them
        if self.settings.get("suspend_in_parallel", True):
            pool = ThreadPool(concurrency)
            pool.map(self.suspend_stack, stacks)
            pool.close()
            pool.join()
        else:
            for stack in stacks:
                self.suspend_stack(stack)

    def get_heat_client(self, configuration):
        return HeatWrapper(**configuration).get_client()

    def suspend_stack(self, stack):
        """
        Suspend the stack.

        """
        configuration = get_xblock_configuration(self.settings, stack.provider)
        heat_client = self.get_heat_client(configuration)

        self.stdout.write("Initializing stack [%s] suspension." % stack.name)

        try:
            heat_stack = heat_client.stacks.get(stack_id=stack.name)
        except HTTPNotFound:
            heat_status = DELETE_STATE
        else:
            heat_status = heat_stack.stack_status

        if heat_status in UP_STATES:
            self.stdout.write("Suspending stack [%s]." % (stack.name))

            # Suspend stack
            heat_client.actions.suspend(stack_id=stack.name)

            # Save status
            stack.status = SUSPEND_ISSUED_STATE
            stack.save()
        else:
            self.stdout.write("Cannot suspend stack [%s] "
                              "with status [%s]." % (stack.name, heat_status))

            # Schedule for retry, if it makes sense to do so
            if (heat_status != DELETE_STATE and
                    'FAILED' not in heat_status):
                stack.status = SUSPEND_RETRY_STATE
            else:
                stack.status = heat_status

            stack.save()
