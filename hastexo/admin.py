"""
Admin registration for hastexo Xblock models
"""
from django import forms
from django.contrib import admin
from student.models import AnonymousUserId

from .common import DELETE_COMPLETE, VALID_STATES, get_xblock_settings
from .models import Stack


def mark_deleted(modeladmin, request, queryset):
    """
    Mark selected stacks as deleted, and reset the provider.

    """
    queryset.update(status=DELETE_COMPLETE, provider="")


mark_deleted.short_description = "Mark selected stacks as DELETE_COMPLETE"


def student_email(stack):
    """
    Fetch the student's email.  This callable should not be used in
    `list_display`, as it would issue a query for every record on the page.

    (Making `student_id` a ForeignKey wouldn't improve performance, as Django
    doesn't support related field lookups (a.k.a. JOINs) on `list_display`.
    However, doing so would allow searching or ordering by email, which is why
    this parenthetical note is here: though not without drawbacks, it may be
    deemed desirable in the future.)

    """
    try:
        anonymous_user_id = AnonymousUserId.objects.get(
            anonymous_user_id=stack.student_id)
    except AnonymousUserId.DoesNotExist:
        return None

    return anonymous_user_id.user.email


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
    actions = (mark_deleted,)
    search_fields = ("name", "course_id", "status", "provider")
    readonly_fields = ("name", student_email, "course_id", "run", "protocol",
                       "port", "ip", "launch_timestamp", "suspend_timestamp",
                       "created_on", "error_msg", "delete_age",)
    exclude = ("student_id", "providers", "hook_script", "hook_events",
               "launch_task_id", "user", "key", "password",)
    ordering = ("-launch_timestamp",)

    def get_changelist_form(self, request, **kwargs):
        return StackAdminForm

    def has_add_permission(self, request, obj=None):
        """
        Adding stacks manually is not supported.

        """
        return False


admin.site.register(Stack, StackAdmin)
