"""
Admin registration for hastexo Xblock models
"""
from django import forms
from django.contrib import admin

from .common import (
    DELETE_COMPLETE,
    SUSPEND_COMPLETE,
    VALID_STATES,
    get_xblock_settings
)
from .models import Stack, StackLog


@admin.action(description="Mark selected stacks as SUSPEND_COMPLETE")
def mark_suspended(modeladmin, request, queryset):
    """
    Mark selected stacks as successfully suspended.

    """
    queryset.update(status=SUSPEND_COMPLETE)


@admin.action(description="Mark selected stacks as DELETE_COMPLETE")
def mark_deleted(modeladmin, request, queryset):
    """
    Mark selected stacks as deleted, and reset the provider.

    """
    queryset.update(status=DELETE_COMPLETE, provider="")


@admin.action(description="Clear stacklog for selected stacks")
def clear_stacklog(self, request, queryset):
    logs = StackLog.objects.filter(stack_id__in=queryset.values('id'))
    logs.delete()
    self.message_user(
        request,
        f'Stacklog cleared for {queryset.count()} stacks!')


def student_email(stack):
    """
    Display the learner email for admin page.

    """
    if stack.learner:
        return stack.learner.email
    else:
        return ""


student_email.short_description = "Email"


class StackAdminForm(forms.ModelForm):
    """
    Custom form for constructing `state` and `provider` choices dynamically
    without the need to modify the model.

    """
    class Meta:
        model = Stack
        exclude = ['id']

    provider = forms.ChoiceField(required=False)
    status = forms.ChoiceField()
    delete_by = forms.DateTimeField(required=False)

    def __init__(self, *args, **kwargs):
        super(StackAdminForm, self).__init__(*args, **kwargs)

        # Gather provider choices.  If the record has `providers` set
        # (signifying the course author limited which providers this course can
        # use), only let the user pick from those.  Otherwise, allow any
        # providers configured in the system.
        if (self.instance and
                len(self.instance.providers)):
            provider_choices = [""] + [p["name"] for p in
                                       self.instance.providers]
        else:
            settings = get_xblock_settings()
            providers = settings.get("providers", {})
            provider_choices = [""] + list(providers)

        self.fields["provider"].choices = [(i, i) for i in provider_choices]
        self.fields["status"].choices = [("", "")] + \
                                        [(i, i) for i in VALID_STATES]


class StackAdmin(admin.ModelAdmin):
    """
    Custom stack admin class.  Uses a custom form, enables searching and
    filtering, and totally excludes fields used by the XBlock solely to
    communicate with tasks or jobs.  Of the remaining fields, only `status` and
    `provider` should be editable.

    Adding stacks manually is forbidden, but deleting records is allowed.  A
    custom action allows marking stacks as `DELETE_COMPLETE` in bulk.

    """
    form = StackAdminForm
    list_display = ("name", "course_id", "status", "provider",
                    "launch_timestamp",)
    list_filter = ("course_id", "status", "provider",)
    list_editable = ("status", "provider")
    list_select_related = True
    actions = [mark_suspended, mark_deleted, clear_stacklog]
    search_fields = ("name", "course_id", "status", "provider")
    readonly_fields = ("name", student_email, "course_id", "run", "protocol",
                       "port", "ip", "launch_timestamp", "suspend_timestamp",
                       "suspend_by", "created_on", "error_msg", "delete_age",)
    exclude = ("student_id", "providers", "hook_script", "hook_events",
               "launch_task_id", "user", "key", "password", "learner")
    ordering = ("-launch_timestamp",)

    def get_changelist_form(self, request, **kwargs):
        return StackAdminForm

    def has_add_permission(self, request, obj=None):
        """
        Adding stacks manually is not supported.

        """
        return False


admin.site.register(Stack, StackAdmin)
