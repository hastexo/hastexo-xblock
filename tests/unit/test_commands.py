from django.core.management import call_command
from django.test import TestCase

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch


class SuspenderTestCase(TestCase):

    @patch('hastexo.jobs.SuspenderJob')
    def test_start_suspender(self, mock_suspender):
        # We need to mock the scheduler here, because we obviously
        # don't want to add an actual recurring job during testing
        with patch('apscheduler.schedulers.blocking.BlockingScheduler'):
            call_command('suspender')

        # Did we create a new suspender job?
        self.assertEqual(mock_suspender.call_count, 1)


class ReaperTestCase(TestCase):

    @patch('hastexo.jobs.ReaperJob')
    def test_start_reaper(self, mock_reaper):
        with patch('apscheduler.schedulers.blocking.BlockingScheduler'):
            call_command('reaper')

        # Did we create a new reaper job?
        self.assertEqual(mock_reaper.call_count, 1)
