import django_filters
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet

from . import models


class PropertyFilterSet(NetBoxModelFilterSet):
    q = django_filters.CharFilter(method='search', label='Search')

    class Meta:
        model = models.Property
        fields = ('id', 'name', 'slug', 'status', 'site_id')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(address__icontains=value))


class UnitFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.Unit
        fields = ('id', 'property_id', 'unit_number', 'status', 'tenant_id')


class TariffPlanFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.TariffPlan
        fields = ('id', 'name', 'slug', 'tariff_type', 'status', 'billing_cycle', 'enabled')


class TariffBundleFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.TariffBundle
        fields = ('id', 'name', 'slug', 'status', 'billing_cycle', 'enabled')


class BillingAccountFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.BillingAccount
        fields = ('id', 'tenant_id', 'status', 'autopay_enabled', 'stripe_customer_id')


class CustomerLabelFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.CustomerLabel
        fields = ('id', 'name', 'slug')


class CustomerProfileFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.CustomerProfile
        fields = ('id', 'account_id', 'billing_type', 'city', 'state_province', 'network_device_id')


class SubscriptionFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.Subscription
        fields = (
            'id', 'account_id', 'unit_id', 'tariff_plan_id', 'tariff_bundle_id', 'cpe_device_id',
            'status', 'service_login', 'ipv4_address', 'stripe_subscription_id'
        )


class InvoiceFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.Invoice
        fields = ('id', 'account_id', 'subscription_id', 'number', 'status', 'payment_method', 'stripe_invoice_id')


class InvoiceLineFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.InvoiceLine
        fields = ('id', 'invoice_id', 'description', 'taxable')


class PaymentFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.Payment
        fields = ('id', 'account_id', 'invoice_id', 'method', 'paid_at', 'reference')


class ScheduledPaymentFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.ScheduledPayment
        fields = ('id', 'account_id', 'invoice_id', 'method', 'status', 'run_at', 'stripe_customer_id', 'stripe_payment_intent_id')


class CustomerDocumentFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.CustomerDocument
        fields = ('id', 'account_id', 'title', 'document_type')


class CustomerCommunicationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.CustomerCommunication
        fields = ('id', 'account_id', 'channel', 'direction', 'occurred_at')


class CustomerNoteFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.CustomerNote
        fields = ('id', 'account_id', 'title', 'due_date', 'completed')


class StripeWebhookEventFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = models.StripeWebhookEvent
        fields = ('id', 'event_id', 'event_type', 'processed', 'livemode', 'account_id', 'invoice_id')
