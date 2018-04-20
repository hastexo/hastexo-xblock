# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hastexo', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='StackLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False,
                                        auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64, db_index=True)),
                ('student_id', models.CharField(max_length=40,
                                                db_index=True)),
                ('course_id', models.CharField(max_length=50, db_index=True)),
                ('provider', models.CharField(max_length=32)),
                ('protocol', models.CharField(max_length=32)),
                ('port', models.IntegerField(null=True)),
                ('status', models.CharField(max_length=32, db_index=True)),
                ('error_msg', models.CharField(max_length=256)),
                ('ip', models.GenericIPAddressField(null=True)),
                ('user', models.CharField(max_length=32)),
                ('launch_task_id', models.CharField(max_length=40)),
                ('launch_timestamp', models.DateTimeField(null=True,
                                                          db_index=True)),
                ('suspend_timestamp', models.DateTimeField(null=True,
                                                           db_index=True)),
                ('created_on', models.DateTimeField(auto_now_add=True,
                                                    db_index=True)),
                ('stack', models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='hastexo.Stack', null=True)
                ),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
