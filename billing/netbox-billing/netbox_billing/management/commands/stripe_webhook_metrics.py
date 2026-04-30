from django.core.management.base import BaseCommand

from netbox_billing import services


class Command(BaseCommand):
    help = 'Print Stripe webhook processing metrics.'

    def handle(self, *args, **options):
        metrics = services.stripe_webhook_metrics()
        self.stdout.write(self.style.SUCCESS('Stripe webhook metrics'))
        self.stdout.write(f"- total_events: {metrics['total_events']}")
        self.stdout.write(f"- processed_events: {metrics['processed_events']}")
        self.stdout.write(f"- failed_events: {metrics['failed_events']}")
        self.stdout.write(f"- pending_events: {metrics['pending_events']}")
        self.stdout.write(f"- duplicate_replays_blocked: {metrics['duplicate_replays_blocked']}")
        self.stdout.write('- by_type:')
        for row in metrics['by_type']:
            self.stdout.write(f"  - {row['event_type']}: {row['count']}")
        self.stdout.write('- recent_failures:')
        for row in metrics['recent_failures']:
            self.stdout.write(f"  - {row['event_id']} ({row['event_type']}): {row['error_message']}")
