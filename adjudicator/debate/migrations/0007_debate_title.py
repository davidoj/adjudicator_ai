# Generated by Django 5.1.5 on 2025-01-28 11:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debate', '0006_debate_evaluation_approvals_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='debate',
            name='title',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
