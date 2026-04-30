from django.core.management.base import BaseCommand

from netbox_billing import models, services


class Command(BaseCommand):
    help = 'Retry failed Stripe webhook events (dead-letter replay).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='Maximum number of events to retry (default: 100)')
        parser.add_argument('--event-type', type=str, default='', help='Optional filter by event_type')
        parser.add_argument('--dry-run', action='store_true', help='List candidates without retrying')

    def handle(self, *args, **options):
        limit = max(1, int(options['limit']))
        event_type = (options.get('event_type') or '').strip()
        dry_run = bool(options.get('dry_run'))

        qs = models.StripeWebhookEvent.objects.filter(processed=False).exclude(error_message='')
        if event_type:
            qs = qs.filter(event_type=event_type)
        qs = qs.order_by('created')[:limit]

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('No failed webhook events found.'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f'Dry-run: {total} failed events selected for retry.'))
            for e in qs:
                self.stdout.write(f'- {e.event_id} ({e.event_type}) error={e.error_message[:120]}')
            return

        success = 0
        failed = 0
        for event in qs:
            try:
                services.process_stripe_webhook_event(event.payload)
                success += 1
                self.stdout.write(self.style.SUCCESS(f'Retried OK: {event.event_id}'))
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f'Retry FAILED: {event.event_id} -> {exc}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Retry summary: total={total}, succeeded={success}, failed={failed}'
            )
        )
