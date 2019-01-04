from django.core.management.base import BaseCommand
from apscheduler.schedulers.blocking import BlockingScheduler

from hastexo.common import get_xblock_settings
from hastexo.jobs import SuspenderJob


class Command(BaseCommand):
    help = 'Suspends stacks automatically'

    def handle(self, *args, **options):
        # Get configuration
        settings = get_xblock_settings()

        # Schedule
        scheduler = BlockingScheduler()
        suspender = SuspenderJob(settings)
        interval = settings.get("suspend_interval", 60)
        scheduler.add_job(suspender.run, 'interval', seconds=interval)
        scheduler.start()
