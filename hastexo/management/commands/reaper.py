from django.core.management.base import BaseCommand
from apscheduler.schedulers.blocking import BlockingScheduler

from hastexo.common import get_xblock_settings
from hastexo.jobs import ReaperJob


class Command(BaseCommand):
    help = """Automates the deletion of stale stacks, i.e. those that have not
    been resumed in a configurable time period"""

    def handle(self, *args, **options):
        # Get configuration
        settings = get_xblock_settings()

        # Schedule
        scheduler = BlockingScheduler()
        job = ReaperJob(settings)
        interval = settings.get("delete_interval", 3600)
        scheduler.add_job(job.run, 'interval', seconds=interval)
        scheduler.start()
