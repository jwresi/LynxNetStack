from django.utils import timezone
from extras.jobs import Job, register_jobs

from . import models, services


class ProcessScheduledPaymentsJob(Job):
    class Meta:
        name = 'Process Scheduled Payments'
        description = 'Processes due scheduled payments and charges Stripe.'

    def run(self, data, commit):
        due = models.ScheduledPayment.objects.filter(
            status=models.ScheduledPaymentStatusChoices.STATUS_SCHEDULED,
            run_at__lte=timezone.now(),
        ).select_related('account', 'invoice')

        self.log_info(f'Found {due.count()} due scheduled payment(s).')
        if not commit:
            self.log_warning('Dry run mode enabled; no Stripe charges will be executed.')
            return

        for scheduled in due:
            ok, detail = services.process_scheduled_payment(scheduled)
            if ok:
                self.log_success(
                    f'Processed scheduled payment {scheduled.pk} for account {scheduled.account_id}. Ref={detail}'
                )
            else:
                self.log_failure(
                    f'Failed scheduled payment {scheduled.pk} for account {scheduled.account_id}. Error={detail}'
                )


register_jobs(ProcessScheduledPaymentsJob)
