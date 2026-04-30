import django_tables2 as tables
from netbox.tables import ChoiceFieldColumn, NetBoxTable

from . import models


class PropertyTable(NetBoxTable):
    status = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.Property
        fields = ('pk', 'id', 'name', 'status', 'site', 'address', 'tags', 'actions')


class UnitTable(NetBoxTable):
    status = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.Unit
        fields = ('pk', 'id', 'property', 'unit_number', 'floor', 'tenant', 'status', 'tags', 'actions')


class TariffPlanTable(NetBoxTable):
    status = ChoiceFieldColumn()
    tariff_type = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.TariffPlan
        fields = (
            'pk', 'id', 'name', 'tariff_type', 'status', 'enabled', 'monthly_price', 'download_kbps',
            'upload_kbps', 'billing_cycle', 'stripe_price_id', 'actions'
        )


class TariffBundleTable(NetBoxTable):
    status = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.TariffBundle
        fields = ('pk', 'id', 'name', 'status', 'enabled', 'price', 'billing_cycle', 'partner', 'actions')


class BillingAccountTable(NetBoxTable):
    status = ChoiceFieldColumn()
    preferred_payment_method = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.BillingAccount
        fields = (
            'pk', 'id', 'tenant', 'status', 'autopay_enabled', 'account_balance',
            'preferred_payment_method', 'billing_email', 'stripe_customer_id', 'actions'
        )


class CustomerProfileTable(NetBoxTable):
    billing_type = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.CustomerProfile
        fields = ('pk', 'id', 'account', 'full_name', 'phone_number', 'billing_type', 'city', 'state_province', 'actions')


class CustomerLabelTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = models.CustomerLabel
        fields = ('pk', 'id', 'name', 'color', 'actions')


class SubscriptionTable(NetBoxTable):
    status = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.Subscription
        fields = (
            'pk', 'id', 'account', 'tariff_plan', 'tariff_bundle', 'service_login', 'ipv4_address', 'cpe_device',
            'status', 'billing_start_date', 'billing_end_date', 'invoiced_until', 'actions'
        )


class InvoiceTable(NetBoxTable):
    status = ChoiceFieldColumn()
    payment_method = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.Invoice
        fields = (
            'pk', 'id', 'number', 'account', 'status', 'date', 'due_date', 'payment_date',
            'total', 'balance_due', 'payment_method', 'actions'
        )


class InvoiceLineTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = models.InvoiceLine
        fields = ('pk', 'id', 'invoice', 'description', 'quantity', 'unit_price', 'line_total', 'taxable', 'actions')


class PaymentTable(NetBoxTable):
    method = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.Payment
        fields = ('pk', 'id', 'account', 'invoice', 'method', 'amount', 'paid_at', 'reference', 'actions')


class ScheduledPaymentTable(NetBoxTable):
    method = ChoiceFieldColumn()
    status = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ScheduledPayment
        fields = (
            'pk', 'id', 'account', 'invoice', 'status', 'method', 'amount', 'currency', 'run_at',
            'processed_at', 'stripe_payment_intent_id', 'external_reference', 'actions'
        )


class CustomerDocumentTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = models.CustomerDocument
        fields = ('pk', 'id', 'account', 'title', 'document_type', 'document_url', 'actions')


class CustomerCommunicationTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = models.CustomerCommunication
        fields = ('pk', 'id', 'account', 'channel', 'subject', 'direction', 'occurred_at', 'actions')


class CustomerNoteTable(NetBoxTable):
    completed = tables.BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = models.CustomerNote
        fields = ('pk', 'id', 'account', 'title', 'due_date', 'completed', 'actions')


class StripeWebhookEventTable(NetBoxTable):
    processed = tables.BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = models.StripeWebhookEvent
        fields = ('pk', 'id', 'event_id', 'event_type', 'processed', 'livemode', 'account', 'invoice', 'created', 'actions')
