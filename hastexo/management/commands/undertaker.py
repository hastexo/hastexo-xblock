from django.core.management.base import BaseCommand
from django.conf import settings as django_settings
from apscheduler.schedulers.blocking import BlockingScheduler

from hastexo.utils import SETTINGS_KEY, DEFAULT_SETTINGS
from hastexo.jobs import UndertakerJob


class Command(BaseCommand):
    help = """Automates the deletion of stale stacks, i.e. those that have not
    been resumed in a configurable time period"""

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
        job = UndertakerJob(settings, self.stdout)
        interval = settings.get("delete_interval", 86400)
        scheduler.add_job(job.run, 'interval', seconds=interval)
        scheduler.start()
