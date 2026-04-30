from netbox.forms import NetBoxModelForm

from . import models


class PropertyForm(NetBoxModelForm):
    class Meta:
        model = models.Property
        fields = ('name', 'slug', 'status', 'site', 'address', 'comments', 'tags')


class UnitForm(NetBoxModelForm):
    class Meta:
        model = models.Unit
        fields = ('property', 'unit_number', 'floor', 'status', 'tenant', 'service_address', 'comments', 'tags')


class TariffPlanForm(NetBoxModelForm):
    class Meta:
        model = models.TariffPlan
        fields = (
            'name', 'slug', 'tariff_type', 'status', 'enabled', 'color', 'currency', 'monthly_price', 'setup_fee',
            'billing_period_months', 'service_description', 'partner', 'vat_included', 'vat_name',
            'download_kbps', 'upload_kbps', 'guaranteed_speed', 'priority', 'aggregation_ratio', 'burst_profile',
            'transaction_category', 'billing_cycle', 'activation_fee', 'activation_fee_when',
            'contract_duration_months', 'automatic_renewal', 'auto_reactivate', 'cancellation_fee',
            'prior_cancellation_fee', 'discount_value', 'discount_type', 'show_tariff_customer_portal',
            'hide_tariff_admin_portal', 'available_locations', 'customer_category', 'customer_labels',
            'available_upgrade_tariffs', 'available_for_social_register', 'stripe_price_id', 'description',
            'comments', 'tags'
        )


class TariffBundleForm(NetBoxModelForm):
    class Meta:
        model = models.TariffBundle
        fields = (
            'name', 'slug', 'status', 'enabled', 'service_description', 'price', 'vat_included', 'vat_name',
            'partner', 'billing_cycle', 'transaction_category', 'activation_fee', 'contract_duration_months',
            'automatic_renewal', 'auto_reactivate', 'cancellation_fee', 'prior_cancellation_fee',
            'discount_value', 'discount_type', 'show_tariff_customer_portal', 'hide_tariff_admin_portal',
            'available_locations', 'customer_category', 'customer_labels', 'included_tariffs', 'comments', 'tags'
        )


class BillingAccountForm(NetBoxModelForm):
    class Meta:
        model = models.BillingAccount
        fields = (
            'tenant', 'status', 'stripe_customer_id', 'autopay_enabled', 'billing_email', 'billing_phone',
            'external_reference', 'account_balance', 'preferred_payment_method', 'comments', 'tags'
        )


class CustomerLabelForm(NetBoxModelForm):
    class Meta:
        model = models.CustomerLabel
        fields = ('name', 'slug', 'color', 'comments', 'tags')


class CustomerProfileForm(NetBoxModelForm):
    class Meta:
        model = models.CustomerProfile
        fields = (
            'account', 'portal_login', 'portal_password', 'billing_type', 'full_name', 'email', 'billing_email',
            'phone_number', 'partner', 'location', 'street', 'zip_code', 'city', 'state_province', 'geodata',
            'date_added', 'category', 'date_of_birth', 'identification', 'preferred_payment', 'address',
            'unit_number', 'last4_ssn', 'preferred_installation_days', 'tv_content_interest', 'coverage_notes',
            'comment', 'network_device', 'labels', 'tags'
        )


class SubscriptionForm(NetBoxModelForm):
    class Meta:
        model = models.Subscription
        fields = (
            'account', 'unit', 'tariff_plan', 'tariff_bundle', 'cpe_device', 'service_login', 'ipv4_address',
            'status', 'start_date', 'end_date', 'billing_start_date', 'billing_end_date', 'invoiced_until',
            'rule', 'price_override', 'stripe_subscription_id', 'stripe_price_id', 'notes', 'tags'
        )


class InvoiceForm(NetBoxModelForm):
    class Meta:
        model = models.Invoice
        fields = (
            'account', 'subscription', 'number', 'status', 'date', 'due_date', 'payment_date',
            'period_start', 'period_end', 'currency', 'subtotal', 'tax', 'total', 'balance_due',
            'payment_method', 'stripe_invoice_id', 'stripe_payment_intent_id', 'comments', 'tags'
        )


class InvoiceLineForm(NetBoxModelForm):
    class Meta:
        model = models.InvoiceLine
        fields = ('invoice', 'description', 'quantity', 'unit_price', 'line_total', 'taxable', 'comments', 'tags')


class PaymentForm(NetBoxModelForm):
    class Meta:
        model = models.Payment
        fields = ('account', 'invoice', 'method', 'amount', 'paid_at', 'reference', 'comments', 'tags')


class ScheduledPaymentForm(NetBoxModelForm):
    class Meta:
        model = models.ScheduledPayment
        fields = (
            'account', 'invoice', 'method', 'amount', 'currency', 'run_at', 'status',
            'stripe_customer_id', 'stripe_payment_method_id', 'stripe_payment_intent_id',
            'description', 'error_message', 'processed_at', 'canceled_at',
            'external_reference', 'comments', 'tags'
        )


class CustomerDocumentForm(NetBoxModelForm):
    class Meta:
        model = models.CustomerDocument
        fields = ('account', 'title', 'document_type', 'document_url', 'comments', 'tags')


class CustomerCommunicationForm(NetBoxModelForm):
    class Meta:
        model = models.CustomerCommunication
        fields = ('account', 'channel', 'subject', 'message', 'direction', 'occurred_at', 'tags')


class CustomerNoteForm(NetBoxModelForm):
    class Meta:
        model = models.CustomerNote
        fields = ('account', 'title', 'note', 'due_date', 'completed', 'tags')


class StripeWebhookEventForm(NetBoxModelForm):
    class Meta:
        model = models.StripeWebhookEvent
        fields = ('event_id', 'event_type', 'livemode', 'processed', 'account', 'invoice', 'payload', 'error_message', 'tags')
