from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_billing', '0004_serviceticket'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ServiceTicket',
        ),
    ]
