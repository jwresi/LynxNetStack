import hashlib
import hmac
import json
import time
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.text import slugify

from tenancy.models import Tenant

from netbox_billing import models as bm


class StripeWebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.actor = get_user_model().objects.create_user(username='webhook_actor', password='x')

        cfg = settings.PLUGINS_CONFIG.setdefault('netbox_billing', {})
        self._old_secret = cfg.get('stripe_webhook_secret', '')
        self._old_actor = cfg.get('webhook_actor_username', '')
        cfg['stripe_webhook_secret'] = 'whsec_test_123'
        cfg['webhook_actor_username'] = self.actor.username

        tenant = Tenant.objects.create(name='Webhook Test Customer', slug=slugify('webhook-test-customer'))
        self.account = bm.BillingAccount.objects.create(
            tenant=tenant,
            status=bm.GenericStatusChoices.STATUS_ACTIVE,
            stripe_customer_id='cus_webhook_001',
            autopay_enabled=True,
            billing_email='webhook@test.local',
            billing_phone='9295550000',
        )
        self.subscription = bm.Subscription.objects.create(
            account=self.account,
            status=bm.SubscriptionStatusChoices.STATUS_ACTIVE,
            service_login='webhook-service-login',
            stripe_subscription_id='sub_webhook_001',
            notes='Webhook test subscription',
        )
        self.invoice = bm.Invoice.objects.create(
            account=self.account,
            subscription=self.subscription,
            number='WEBHOOK-INV-001',
            status=bm.InvoiceStatusChoices.STATUS_OPEN,
            date=date.today(),
            currency=bm.CurrencyChoices.CURRENCY_USD,
            subtotal=Decimal('100.00'),
            tax=Decimal('8.00'),
            total=Decimal('108.00'),
            balance_due=Decimal('108.00'),
            stripe_invoice_id='in_webhook_001',
            stripe_payment_intent_id='pi_webhook_001',
        )

    def tearDown(self):
        cfg = settings.PLUGINS_CONFIG.setdefault('netbox_billing', {})
        cfg['stripe_webhook_secret'] = self._old_secret
        cfg['webhook_actor_username'] = self._old_actor

    def _sign(self, payload: bytes, ts: int | None = None):
        ts = ts or int(time.time())
        signed = f'{ts}.{payload.decode("utf-8")}'.encode('utf-8')
        digest = hmac.new(b'whsec_test_123', signed, hashlib.sha256).hexdigest()
        return f't={ts},v1={digest}'

    def _post_event(self, event: dict, signature: str | None = None):
        payload = json.dumps(event).encode('utf-8')
        headers = {}
        if signature is not None:
            headers['HTTP_STRIPE_SIGNATURE'] = signature
        return self.client.post(
            reverse('plugins:netbox_billing:stripe_webhook'),
            data=payload,
            content_type='application/json',
            **headers,
        )

    def test_rejects_invalid_signature(self):
        event = {'id': 'evt_invalid_sig', 'type': 'invoice.paid', 'data': {'object': {'id': 'in_webhook_001'}}}
        response = self._post_event(event, signature='t=1,v1=bad')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json().get('ok', True))

    def test_invoice_paid_marks_invoice_and_stores_event(self):
        event = {
            'id': 'evt_invoice_paid_001',
            'type': 'invoice.paid',
            'livemode': False,
            'data': {'object': {'id': 'in_webhook_001', 'metadata': {'invoice_id': str(self.invoice.pk)}}},
        }
        payload = json.dumps(event).encode('utf-8')
        response = self._post_event(event, signature=self._sign(payload))
        self.assertEqual(response.status_code, 200)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, bm.InvoiceStatusChoices.STATUS_PAID)
        self.assertEqual(self.invoice.balance_due, Decimal('0.00'))

        webhook = bm.StripeWebhookEvent.objects.get(event_id='evt_invoice_paid_001')
        self.assertTrue(webhook.processed)
        self.assertEqual(webhook.invoice_id, self.invoice.pk)
        self.assertEqual(webhook.account_id, self.account.pk)

    def test_payment_intent_succeeded_is_idempotent(self):
        event = {
            'id': 'evt_pi_succeeded_001',
            'type': 'payment_intent.succeeded',
            'livemode': False,
            'data': {
                'object': {
                    'id': 'pi_webhook_001',
                    'amount_received': 10800,
                    'currency': 'usd',
                    'metadata': {
                        'billing_account_id': str(self.account.pk),
                        'invoice_id': str(self.invoice.pk),
                    },
                }
            },
        }
        payload = json.dumps(event).encode('utf-8')
        sig = self._sign(payload)

        first = self._post_event(event, signature=sig)
        second = self._post_event(event, signature=sig)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        payments = bm.Payment.objects.filter(reference='pi_webhook_001')
        self.assertEqual(payments.count(), 1)

        webhook = bm.StripeWebhookEvent.objects.get(event_id='evt_pi_succeeded_001')
        self.assertTrue(webhook.processed)

    def test_subscription_updated_syncs_status(self):
        event = {
            'id': 'evt_sub_updated_001',
            'type': 'customer.subscription.updated',
            'livemode': False,
            'data': {
                'object': {
                    'id': 'sub_webhook_001',
                    'status': 'past_due',
                    'metadata': {'billing_account_id': str(self.account.pk)},
                }
            },
        }
        payload = json.dumps(event).encode('utf-8')
        response = self._post_event(event, signature=self._sign(payload))
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, bm.SubscriptionStatusChoices.STATUS_PAST_DUE)

    def test_duplicate_replay_counter_increments(self):
        event = {
            'id': 'evt_replay_counter_001',
            'type': 'invoice.paid',
            'livemode': False,
            'data': {'object': {'id': 'in_webhook_001', 'metadata': {'invoice_id': str(self.invoice.pk)}}},
        }
        payload = json.dumps(event).encode('utf-8')
        sig = self._sign(payload)

        first = self._post_event(event, signature=sig)
        second = self._post_event(event, signature=sig)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        record = bm.StripeWebhookEvent.objects.get(event_id='evt_replay_counter_001')
        meta = (record.payload or {}).get('_meta', {})
        self.assertEqual(int(meta.get('replay_count', 0)), 1)
