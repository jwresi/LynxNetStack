# Generated manually for NetBox runtime (makemigrations disabled in container)

from django.conf import settings
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0121_customfield_related_object_filter'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('netbox_billing', '0003_scheduledpayment'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('title', models.CharField(max_length=150)),
                ('ticket_type', models.CharField(default='support', max_length=20)),
                ('status', models.CharField(default='open', max_length=30)),
                ('priority', models.CharField(blank=True, default='normal', max_length=20)),
                ('scheduled_for', models.DateTimeField(blank=True, null=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('external_reference', models.CharField(blank=True, max_length=100)),
                ('description', models.TextField(blank=True)),
                ('resolution_notes', models.TextField(blank=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tickets', to='netbox_billing.billingaccount')),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_service_tickets', to=settings.AUTH_USER_MODEL)),
                ('opened_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opened_service_tickets', to=settings.AUTH_USER_MODEL)),
                ('subscription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tickets', to='netbox_billing.subscription')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'service ticket',
                'verbose_name_plural': 'service tickets',
                'ordering': ('-created',),
            },
            bases=(models.Model,),
        ),
    ]
