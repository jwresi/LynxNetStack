from django.core.management.base import BaseCommand
from django.utils import timezone

from netbox_billing import models, services


class Command(BaseCommand):
    help = 'Process due scheduled payments and charge Stripe.'

    def handle(self, *args, **options):
        due = models.ScheduledPayment.objects.filter(
            status=models.ScheduledPaymentStatusChoices.STATUS_SCHEDULED,
            run_at__lte=timezone.now(),
        ).select_related('account', 'invoice')

        self.stdout.write(f'Found {due.count()} due scheduled payment(s).')
        for scheduled in due:
            ok, detail = services.process_scheduled_payment(scheduled)
            if ok:
                self.stdout.write(self.style.SUCCESS(f'Processed #{scheduled.pk}: {detail}'))
            else:
                self.stdout.write(self.style.ERROR(f'Failed #{scheduled.pk}: {detail}'))
