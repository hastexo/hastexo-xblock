# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hastexo', '0002_stacklog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stack',
            name='error_msg',
            field=models.CharField(max_length=256, blank=True),
        ),
        migrations.AlterField(
            model_name='stack',
            name='key',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='stack',
            name='launch_task_id',
            field=models.CharField(max_length=40, blank=True),
        ),
        migrations.AlterField(
            model_name='stack',
            name='password',
            field=models.CharField(max_length=128, blank=True),
        ),
        migrations.AlterField(
            model_name='stack',
            name='protocol',
            field=models.CharField(max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='stack',
            name='provider',
            field=models.CharField(max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='stack',
            name='status',
            field=models.CharField(db_index=True, max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='stack',
            name='user',
            field=models.CharField(max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='stacklog',
            name='error_msg',
            field=models.CharField(max_length=256, blank=True),
        ),
        migrations.AlterField(
            model_name='stacklog',
            name='launch_task_id',
            field=models.CharField(max_length=40, blank=True),
        ),
        migrations.AlterField(
            model_name='stacklog',
            name='protocol',
            field=models.CharField(max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='stacklog',
            name='provider',
            field=models.CharField(max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='stacklog',
            name='status',
            field=models.CharField(db_index=True, max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='stacklog',
            name='user',
            field=models.CharField(max_length=32, blank=True),
        ),
    ]
