"""
Tests for admin.py

"""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.http import HttpRequest
from django.test import TestCase
from django.test.client import Client
from django.urls import reverse
from student.models import AnonymousUserId
from hastexo.admin import StackAdmin
from hastexo.models import Stack


class TestHastexoStackAdmin(TestCase):
    """
    Test class for StackAdmin

    """
    def setUp(self):
        self.username = "bogus"
        self.email = "bogus@example.com"
        self.student_id = "bogus_student_id"
        self.course_id = "bogus_course_id"
        self.stack_name = "bogus_stack_name"
        self.provider = "bogus_provider"
        self.providers = [
            {"name": "provider1",
             "capacity": 1,
             "template": "tmpl1",
             "environment": "env1"},
            {"name": "provider2",
             "capacity": 2,
             "template": "tmpl2",
             "environment": "env2"},
            {"name": "provider3",
             "capacity": -1,
             "template": "tmpl3",
             "environment": "env3"}
        ]
        self.user = User.objects.create_user(
            self.username,
            self.email,
            "password"
        )
        self.anonymous_user_id = AnonymousUserId.objects.create(
            user=self.user,
            anonymous_user_id=self.student_id
        )
        self.stack = Stack.objects.create(
            student_id=self.student_id,
            course_id=self.course_id,
            name=self.stack_name,
            status="CREATE_COMPLETE",
            provider=self.provider,
            providers=self.providers
        )
        self.stack_admin = StackAdmin(Stack, AdminSite())
        self.request = HttpRequest()
        self.admin = User.objects.create_superuser(
            'admin',
            'admin@example.com',
            'password'
        )
        self.client = Client()
        self.client.login(username='admin', password='password')

    def test_fields_in_admin_form(self):
        """
        Tests presence of form fields.

        """
        form = self.stack_admin.get_form(self.request, self.stack)
        self.assertEqual(
            list(form.base_fields),
            ["provider", "status", "delete_by"]
        )

    def test_save_action_admin_form(self):
        """
        Tests save action.

        """
        form = self.stack_admin.get_form(self.request)(
            instance=self.stack,
            data={
                "status": "DELETE_COMPLETE",
                "provider": "",
                "delete_by": None
            }
        )
        self.assertTrue(form.is_valid())
        form.save()
        stack = Stack.objects.get(pk=self.stack.id)
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.provider, "")

    def test_name_in_changelist(self):
        response = self.client.get(reverse('admin:hastexo_stack_changelist'))
        self.assertContains(response, self.stack_name)

    def test_no_stack_providers_in_change_page(self):
        self.stack.providers = {}
        self.stack.save()
        url = reverse('admin:hastexo_stack_change', args=(self.stack.id,))
        response = self.client.get(url)
        self.assertNotContains(response, "provider3")

    def test_email_in_change_page(self):
        url = reverse('admin:hastexo_stack_change', args=(self.stack.id,))
        response = self.client.get(url)
        self.assertContains(response, self.email)

    def test_no_email_in_change_page(self):
        self.anonymous_user_id.delete()
        url = reverse('admin:hastexo_stack_change', args=(self.stack.id,))
        response = self.client.get(url)
        self.assertNotContains(response, self.email)
