from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('debate', '0002_creditbalance_debate_credit_cost'),
    ]

    operations = [
        migrations.CreateModel(
            name='IPCreditUsage',
            fields=[
                ('ip_address', models.GenericIPAddressField(primary_key=True)),
                ('credits_used', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
        ),
    ] 