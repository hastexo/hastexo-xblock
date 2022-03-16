from django.contrib.auth.models import User
from django.test import TestCase

from common.djangoapps.student.models import AnonymousUserId

from hastexo.models import Stack, StackLog


class TestHastexoModels(TestCase):
    def setUp(self):
        self.student_id = 'bogus_student_id'
        self.course_id = 'bogus_course_id'
        self.stack_name = 'bogus_stack_name'

        user = User.objects.create_user(
            "fake_user",
            "user@example.com",
            "password"
        )
        learner = AnonymousUserId.objects.create(
            user=user,
            anonymous_user_id=self.student_id).user

        self.learner = learner

    def test_logging(self):
        log = StackLog.objects.all()
        self.assertEqual(len(log), 0)

        stack, _ = Stack.objects.get_or_create(
            student_id=self.student_id,
            course_id=self.course_id,
            name=self.stack_name,
            learner=self.learner
        )
        stack.status = 'CREATE_IN_PROGRESS'
        stack.save(update_fields=["status"])
        stack = Stack.objects.all()[0]
        stack.status = 'CREATE_IN_PROGRESS'
        stack.save(update_fields=["status"])
        stack = Stack.objects.all()[0]
        stack.status = 'CREATE_IN_PROGRESS'
        stack.save(update_fields=["status"])
        stack = Stack.objects.all()[0]
        stack.status = 'CREATE_COMPLETE'
        stack.save(update_fields=["status"])
        stack = Stack.objects.all()[0]
        stack.status = 'SUSPEND_PENDING'
        stack.save(update_fields=["status"])
        stack.status = 'SUSPEND_FAILED'
        stack.save(update_fields=["status"])
        stack = Stack.objects.all()[0]
        stack.status = 'SUSPEND_PENDING'
        stack.save(update_fields=["status"])
        stack.status = 'SUSPEND_FAILED'
        stack.save(update_fields=["status"])
        stack = Stack.objects.all()[0]
        stack.status = 'SUSPEND_PENDING'
        stack.save(update_fields=["status"])
        stack.status = 'SUSPEND_COMPLETE'
        stack.save(update_fields=["status"])

        log = StackLog.objects.all()
        self.assertEqual(len(log), 8)
        self.assertEqual(log[0].status, 'CREATE_IN_PROGRESS')
        self.assertEqual(log[1].status, 'CREATE_COMPLETE')
        self.assertEqual(log[2].status, 'SUSPEND_PENDING')
        self.assertEqual(log[3].status, 'SUSPEND_FAILED')
        self.assertEqual(log[4].status, 'SUSPEND_PENDING')
        self.assertEqual(log[5].status, 'SUSPEND_FAILED')
        self.assertEqual(log[6].status, 'SUSPEND_PENDING')
        self.assertEqual(log[7].status, 'SUSPEND_COMPLETE')
