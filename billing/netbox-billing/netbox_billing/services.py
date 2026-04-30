import hashlib
import hmac
import json
import time
from decimal import Decimal

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from . import models


def _stripe_secret_key():
    plugin_cfg = settings.PLUGINS_CONFIG.get('netbox_billing', {})
    return plugin_cfg.get('stripe_api_key') or getattr(settings, 'STRIPE_API_KEY', '')


def _stripe_webhook_secret():
    plugin_cfg = settings.PLUGINS_CONFIG.get('netbox_billing', {})
    return plugin_cfg.get('stripe_webhook_secret') or getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')


def _currency_amount_to_cents(amount: Decimal) -> int:
    return int((amount * Decimal('100')).quantize(Decimal('1')))


def _load_stripe():
    try:
        import stripe
    except ImportError as exc:
        raise RuntimeError('Stripe SDK is not installed in this environment.') from exc

    secret_key = _stripe_secret_key()
    if not secret_key:
        raise RuntimeError('Stripe is not configured. Set PLUGINS_CONFIG[\'netbox_billing\'][\'stripe_api_key\'].')

    stripe.api_key = secret_key
    return stripe


def create_payment_intent(
    *,
    amount: Decimal,
    currency: str,
    customer_id: str,
    payment_method_id: str = '',
    description: str = '',
    metadata: dict | None = None,
):
    stripe = _load_stripe()
    params = {
        'amount': _currency_amount_to_cents(amount),
        'currency': currency.lower(),
        'confirm': True,
        'off_session': True,
        'description': description or 'NetBox Billing payment',
        'metadata': metadata or {},
    }
    if customer_id:
        params['customer'] = customer_id
    if payment_method_id:
        params['payment_method'] = payment_method_id
    return stripe.PaymentIntent.create(**params)


def record_successful_payment(
    *,
    account: models.BillingAccount,
    invoice: models.Invoice | None,
    method: str,
    amount: Decimal,
    reference: str,
    comments: str,
):
    payment, _ = models.Payment.objects.get_or_create(
        reference=reference,
        defaults={
            'account': account,
            'invoice': invoice,
            'method': method,
            'amount': amount,
            'paid_at': timezone.now().date(),
            'comments': comments,
        },
    )
    if invoice and invoice.status != models.InvoiceStatusChoices.STATUS_PAID:
        invoice.status = models.InvoiceStatusChoices.STATUS_PAID
        invoice.payment_date = timezone.now().date()
        invoice.balance_due = Decimal('0')
        invoice.save()
    return payment


def process_scheduled_payment(scheduled_payment: models.ScheduledPayment) -> tuple[bool, str]:
    if scheduled_payment.status in (
        models.ScheduledPaymentStatusChoices.STATUS_SUCCEEDED,
        models.ScheduledPaymentStatusChoices.STATUS_CANCELED,
    ):
        return True, 'Skipping terminal scheduled payment.'

    account = scheduled_payment.account
    customer_id = scheduled_payment.stripe_customer_id or account.stripe_customer_id
    if not customer_id:
        scheduled_payment.status = models.ScheduledPaymentStatusChoices.STATUS_FAILED
        scheduled_payment.error_message = 'Missing Stripe customer ID on account or scheduled payment.'
        scheduled_payment.processed_at = timezone.now()
        scheduled_payment.save()
        return False, scheduled_payment.error_message

    try:
        scheduled_payment.status = models.ScheduledPaymentStatusChoices.STATUS_PROCESSING
        scheduled_payment.error_message = ''
        scheduled_payment.save()

        intent = create_payment_intent(
            amount=scheduled_payment.amount,
            currency=scheduled_payment.currency,
            customer_id=customer_id,
            payment_method_id=scheduled_payment.stripe_payment_method_id,
            description=scheduled_payment.description or f'Scheduled payment #{scheduled_payment.pk}',
            metadata={
                'billing_account_id': str(account.pk),
                'scheduled_payment_id': str(scheduled_payment.pk),
                'invoice_id': str(scheduled_payment.invoice_id or ''),
            },
        )

        scheduled_payment.status = models.ScheduledPaymentStatusChoices.STATUS_SUCCEEDED
        scheduled_payment.processed_at = timezone.now()
        scheduled_payment.stripe_payment_intent_id = intent.id
        scheduled_payment.external_reference = intent.id
        scheduled_payment.save()

        record_successful_payment(
            account=account,
            invoice=scheduled_payment.invoice,
            method=scheduled_payment.method,
            amount=scheduled_payment.amount,
            reference=intent.id,
            comments=f'Created from scheduled payment #{scheduled_payment.pk}',
        )
        return True, intent.id
    except Exception as exc:
        scheduled_payment.status = models.ScheduledPaymentStatusChoices.STATUS_FAILED
        scheduled_payment.error_message = str(exc)
        scheduled_payment.processed_at = timezone.now()
        scheduled_payment.save()
        return False, str(exc)


def verify_stripe_webhook_signature(payload: bytes, signature_header: str) -> None:
    """
    Verify Stripe-style webhook signature without requiring Stripe SDK.
    Header format: t=<timestamp>,v1=<signature>[,v1=<signature2>...]
    """
    secret = _stripe_webhook_secret()
    if not secret:
        raise RuntimeError('Stripe webhook secret is not configured.')
    if not signature_header:
        raise ValueError('Missing Stripe-Signature header.')

    parts = [segment.strip() for segment in signature_header.split(',') if segment.strip()]
    values = {}
    for part in parts:
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        values.setdefault(key, []).append(value)

    timestamps = values.get('t', [])
    signatures = values.get('v1', [])
    if not timestamps or not signatures:
        raise ValueError('Invalid Stripe-Signature header.')

    timestamp = int(timestamps[0])
    # Mirror Stripe default tolerance window.
    tolerance_seconds = 300
    if abs(int(time.time()) - timestamp) > tolerance_seconds:
        raise ValueError('Webhook signature timestamp is outside tolerance window.')

    signed_payload = f'{timestamp}.{payload.decode("utf-8")}'.encode('utf-8')
    expected = hmac.new(secret.encode('utf-8'), signed_payload, hashlib.sha256).hexdigest()

    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise ValueError('Webhook signature verification failed.')


def _safe_dict(obj):
    if isinstance(obj, dict):
        return obj
    return {}


def _sync_subscription_status(stripe_status: str) -> str:
    mapping = {
        'trialing': models.SubscriptionStatusChoices.STATUS_TRIAL,
        'active': models.SubscriptionStatusChoices.STATUS_ACTIVE,
        'past_due': models.SubscriptionStatusChoices.STATUS_PAST_DUE,
        'unpaid': models.SubscriptionStatusChoices.STATUS_PAST_DUE,
        'canceled': models.SubscriptionStatusChoices.STATUS_CANCELED,
        'incomplete': models.SubscriptionStatusChoices.STATUS_SUSPENDED,
        'incomplete_expired': models.SubscriptionStatusChoices.STATUS_SUSPENDED,
        'paused': models.SubscriptionStatusChoices.STATUS_SUSPENDED,
    }
    return mapping.get((stripe_status or '').lower(), models.SubscriptionStatusChoices.STATUS_ACTIVE)


def process_stripe_webhook_event(event: dict) -> tuple[models.StripeWebhookEvent, bool, str]:
    """
    Process a normalized Stripe event payload.
    Returns: (event_record, created, detail_message)
    """
    event_id = (event or {}).get('id', '')
    event_type = (event or {}).get('type', '')
    livemode = bool((event or {}).get('livemode', False))
    payload_obj = _safe_dict(((event or {}).get('data') or {}).get('object'))
    metadata = _safe_dict(payload_obj.get('metadata'))

    if not event_id or not event_type:
        raise ValueError('Webhook event must include id and type.')

    webhook_event, created = models.StripeWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            'event_type': event_type,
            'livemode': livemode,
            'processed': False,
            'payload': event,
        },
    )
    if not created and webhook_event.processed:
        payload_data = _safe_dict(webhook_event.payload)
        meta = _safe_dict(payload_data.get('_meta'))
        replay_count = int(meta.get('replay_count', 0)) + 1
        meta['replay_count'] = replay_count
        meta['last_replay_at'] = timezone.now().isoformat()
        payload_data['_meta'] = meta
        webhook_event.payload = payload_data
        webhook_event.save(update_fields=['payload', 'last_updated'])
        return webhook_event, False, 'Duplicate event already processed.'

    webhook_event.event_type = event_type
    webhook_event.livemode = livemode
    webhook_event.payload = event
    webhook_event.error_message = ''
    webhook_event.save(update_fields=['event_type', 'livemode', 'payload', 'error_message', 'last_updated'])

    linked_account = None
    linked_invoice = None

    try:
        if event_type == 'invoice.paid':
            stripe_invoice_id = payload_obj.get('id', '')
            if stripe_invoice_id:
                linked_invoice = models.Invoice.objects.filter(stripe_invoice_id=stripe_invoice_id).first()
            if not linked_invoice and metadata.get('invoice_id'):
                linked_invoice = models.Invoice.objects.filter(pk=metadata.get('invoice_id')).first()
            if linked_invoice:
                linked_account = linked_invoice.account
                linked_invoice.status = models.InvoiceStatusChoices.STATUS_PAID
                linked_invoice.payment_date = timezone.now().date()
                linked_invoice.balance_due = Decimal('0.00')
                linked_invoice.save(update_fields=['status', 'payment_date', 'balance_due', 'last_updated'])

        elif event_type == 'payment_intent.succeeded':
            intent_id = payload_obj.get('id', '')
            amount_received = Decimal(payload_obj.get('amount_received', 0)) / Decimal('100')
            currency = (payload_obj.get('currency') or models.CurrencyChoices.CURRENCY_USD).lower()

            if metadata.get('invoice_id'):
                linked_invoice = models.Invoice.objects.filter(pk=metadata.get('invoice_id')).first()
            if not linked_invoice and intent_id:
                linked_invoice = models.Invoice.objects.filter(stripe_payment_intent_id=intent_id).first()

            if metadata.get('billing_account_id'):
                linked_account = models.BillingAccount.objects.filter(pk=metadata.get('billing_account_id')).first()
            if not linked_account and linked_invoice:
                linked_account = linked_invoice.account

            if linked_account and intent_id:
                method = models.PaymentMethodChoices.METHOD_CREDIT_CARD
                comments = f'Stripe webhook ({event_type}, currency={currency})'
                record_successful_payment(
                    account=linked_account,
                    invoice=linked_invoice,
                    method=method,
                    amount=amount_received,
                    reference=intent_id,
                    comments=comments,
                )

        elif event_type == 'customer.subscription.updated':
            subscription_id = payload_obj.get('id', '')
            stripe_status = payload_obj.get('status', '')
            if subscription_id:
                subscription = models.Subscription.objects.filter(stripe_subscription_id=subscription_id).first()
                if subscription:
                    subscription.status = _sync_subscription_status(stripe_status)
                    subscription.save(update_fields=['status', 'last_updated'])
                    linked_account = subscription.account

        # Optional fallback linkage for audit visibility.
        if not linked_account and metadata.get('billing_account_id'):
            linked_account = models.BillingAccount.objects.filter(pk=metadata.get('billing_account_id')).first()
        if not linked_invoice and metadata.get('invoice_id'):
            linked_invoice = models.Invoice.objects.filter(pk=metadata.get('invoice_id')).first()

        webhook_event.account = linked_account
        webhook_event.invoice = linked_invoice
        webhook_event.processed = True
        webhook_event.error_message = ''
        webhook_event.save(update_fields=['account', 'invoice', 'processed', 'error_message', 'last_updated'])
        return webhook_event, created, 'Processed successfully.'
    except Exception as exc:
        webhook_event.account = linked_account
        webhook_event.invoice = linked_invoice
        webhook_event.processed = False
        webhook_event.error_message = str(exc)
        webhook_event.save(update_fields=['account', 'invoice', 'processed', 'error_message', 'last_updated'])
        raise


def parse_and_process_stripe_webhook(payload: bytes, signature_header: str) -> tuple[models.StripeWebhookEvent, bool, str]:
    verify_stripe_webhook_signature(payload, signature_header)
    data = json.loads(payload.decode('utf-8'))
    return process_stripe_webhook_event(data)


def stripe_webhook_metrics() -> dict:
    qs = models.StripeWebhookEvent.objects.all()
    total = qs.count()
    processed = qs.filter(processed=True).count()
    failed = qs.filter(processed=False).exclude(error_message='').count()
    pending = qs.filter(processed=False, error_message='').count()

    by_type = list(
        qs.values('event_type')
        .order_by('event_type')
        .annotate(count=Count('id'))
    )

    duplicate_replays_blocked = 0
    for event in qs.only('payload'):
        payload_data = _safe_dict(event.payload)
        meta = _safe_dict(payload_data.get('_meta'))
        duplicate_replays_blocked += int(meta.get('replay_count', 0) or 0)

    recent_failures = list(
        qs.filter(processed=False)
        .exclude(error_message='')
        .order_by('-last_updated')
        .values('event_id', 'event_type', 'error_message', 'last_updated')[:20]
    )

    return {
        'total_events': total,
        'processed_events': processed,
        'failed_events': failed,
        'pending_events': pending,
        'duplicate_replays_blocked': duplicate_replays_blocked,
        'by_type': by_type,
        'recent_failures': recent_failures,
    }
