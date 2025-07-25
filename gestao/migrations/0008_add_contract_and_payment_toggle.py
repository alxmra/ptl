# Generated manually to avoid ManyToManyField through conflict

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gestao', '0007_add_bonus_penalty'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='contract_hourly_rate',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Hourly rate for contracted employees (overrides workblock rates)', max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='employeeworkassignment',
            name='receives_payment',
            field=models.BooleanField(default=True, help_text='Whether this employee receives payment for this workblock'),
        ),
    ]
