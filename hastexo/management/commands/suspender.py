from django.core.management.base import BaseCommand
from django.conf import settings as django_settings
from apscheduler.schedulers.blocking import BlockingScheduler

from hastexo.utils import SETTINGS_KEY, DEFAULT_SETTINGS
from hastexo.jobs import SuspenderJob


class Command(BaseCommand):
    help = 'Suspends stacks automatically'

    def handle(self, *args, **options):
        # Get configuration
        xblock_settings = django_settings.XBLOCK_SETTINGS
        if xblock_settings:
            settings = xblock_settings.get(SETTINGS_KEY,
                                           DEFAULT_SETTINGS)
        else:
            settings = DEFAULT_SETTINGS

        # Schedule
        scheduler = BlockingScheduler()
        suspender = SuspenderJob(settings, self.stdout)
        interval = settings.get("suspend_interval", 60)
        scheduler.add_job(suspender.run, 'interval', seconds=interval)
        scheduler.start()
