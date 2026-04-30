from datetime import date

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel
from utilities.choices import ChoiceSet
from utilities.fields import ColorField


class CurrencyChoices(ChoiceSet):
    CURRENCY_USD = 'usd'

    CHOICES = [
        (CURRENCY_USD, 'USD'),
        ('eur', 'EUR'),
    ]


class GenericStatusChoices(ChoiceSet):
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'

    CHOICES = [
        (STATUS_ACTIVE, 'Active', 'green'),
        (STATUS_INACTIVE, 'Inactive', 'red'),
    ]


class SubscriptionStatusChoices(ChoiceSet):
    STATUS_TRIAL = 'trial'
    STATUS_ACTIVE = 'active'
    STATUS_PAST_DUE = 'past_due'
    STATUS_SUSPENDED = 'suspended'
    STATUS_CANCELED = 'canceled'

    CHOICES = [
        (STATUS_TRIAL, 'Trial', 'cyan'),
        (STATUS_ACTIVE, 'Active', 'green'),
        (STATUS_PAST_DUE, 'Past Due', 'orange'),
        (STATUS_SUSPENDED, 'Suspended', 'red'),
        (STATUS_CANCELED, 'Canceled', 'gray'),
    ]


class InvoiceStatusChoices(ChoiceSet):
    STATUS_DRAFT = 'draft'
    STATUS_OPEN = 'open'
    STATUS_PAID = 'paid'
    STATUS_VOID = 'void'
    STATUS_UNCOLLECTIBLE = 'uncollectible'

    CHOICES = [
        (STATUS_DRAFT, 'Draft', 'yellow'),
        (STATUS_OPEN, 'Open', 'blue'),
        (STATUS_PAID, 'Paid', 'green'),
        (STATUS_VOID, 'Void', 'gray'),
        (STATUS_UNCOLLECTIBLE, 'Uncollectible', 'red'),
    ]


class BillingTypeChoices(ChoiceSet):
    TYPE_RECURRING = 'recurring'
    TYPE_PREPAID = 'prepaid'
    TYPE_ONE_TIME = 'one_time'

    CHOICES = [
        (TYPE_RECURRING, 'Recurring'),
        (TYPE_PREPAID, 'Prepaid'),
        (TYPE_ONE_TIME, 'One-time'),
    ]


class PaymentMethodChoices(ChoiceSet):
    METHOD_CASH = 'cash'
    METHOD_BANK_TRANSFER = 'bank_transfer'
    METHOD_CREDIT_CARD = 'credit_card'
    METHOD_OTHER = 'other'
    METHOD_REFILL_CARD = 'refill_card'
    METHOD_QUICKBOOKS = 'quickbooks'

    CHOICES = [
        (METHOD_CASH, 'Cash'),
        (METHOD_BANK_TRANSFER, 'Bank transfer'),
        (METHOD_CREDIT_CARD, 'Credit card'),
        (METHOD_OTHER, 'Other'),
        (METHOD_REFILL_CARD, 'Refill card'),
        (METHOD_QUICKBOOKS, 'QuickBooks'),
    ]


class ScheduledPaymentStatusChoices(ChoiceSet):
    STATUS_SCHEDULED = 'scheduled'
    STATUS_PROCESSING = 'processing'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_CANCELED = 'canceled'

    CHOICES = [
        (STATUS_SCHEDULED, 'Scheduled', 'cyan'),
        (STATUS_PROCESSING, 'Processing', 'blue'),
        (STATUS_SUCCEEDED, 'Succeeded', 'green'),
        (STATUS_FAILED, 'Failed', 'red'),
        (STATUS_CANCELED, 'Canceled', 'gray'),
    ]


class TariffTypeChoices(ChoiceSet):
    TYPE_INTERNET = 'internet'
    TYPE_VOICE = 'voice'
    TYPE_RECURRING = 'recurring'
    TYPE_ONE_TIME = 'one_time'
    TYPE_BUNDLE = 'bundle'

    CHOICES = [
        (TYPE_INTERNET, 'Internet', 'green'),
        (TYPE_VOICE, 'Voice', 'blue'),
        (TYPE_RECURRING, 'Recurring', 'cyan'),
        (TYPE_ONE_TIME, 'One-time', 'purple'),
        (TYPE_BUNDLE, 'Bundle', 'orange'),
    ]


class DiscountTypeChoices(ChoiceSet):
    TYPE_FIXED = 'fixed_sum'
    TYPE_PERCENT = 'percent'

    CHOICES = [
        (TYPE_FIXED, 'Fixed sum'),
        (TYPE_PERCENT, 'Percent'),
    ]


class BillingCycleChoices(ChoiceSet):
    CYCLE_MONTHLY = 'monthly'
    CYCLE_QUARTERLY = 'quarterly'
    CYCLE_YEARLY = 'yearly'

    CHOICES = [
        (CYCLE_MONTHLY, 'Monthly'),
        (CYCLE_QUARTERLY, 'Quarterly'),
        (CYCLE_YEARLY, 'Yearly'),
    ]


class Property(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    status = models.CharField(max_length=50, choices=GenericStatusChoices, default=GenericStatusChoices.STATUS_ACTIVE)
    site = models.ForeignKey('dcim.Site', on_delete=models.PROTECT, related_name='billing_properties', null=True, blank=True)
    address = models.TextField(blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)
        verbose_name = _('property')
        verbose_name_plural = _('properties')

    def __str__(self):
        return self.name

    def get_status_color(self):
        return GenericStatusChoices.colors.get(self.status)

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:property', args=[self.pk])


class Unit(NetBoxModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='units')
    unit_number = models.CharField(max_length=50)
    floor = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=50, choices=GenericStatusChoices, default=GenericStatusChoices.STATUS_ACTIVE)
    tenant = models.ForeignKey('tenancy.Tenant', on_delete=models.PROTECT, related_name='billing_units', null=True, blank=True)
    service_address = models.TextField(blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('property__name', 'unit_number')
        unique_together = ('property', 'unit_number')
        verbose_name = _('unit')
        verbose_name_plural = _('units')

    def __str__(self):
        return f'{self.property.name} / {self.unit_number}'

    def get_status_color(self):
        return GenericStatusChoices.colors.get(self.status)

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:unit', args=[self.pk])


class TariffPlan(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    tariff_type = models.CharField(max_length=20, choices=TariffTypeChoices, default=TariffTypeChoices.TYPE_INTERNET)
    status = models.CharField(max_length=50, choices=GenericStatusChoices, default=GenericStatusChoices.STATUS_ACTIVE)
    enabled = models.BooleanField(default=True)
    color = ColorField(default='00bcd4')
    currency = models.CharField(max_length=3, choices=CurrencyChoices, default=CurrencyChoices.CURRENCY_USD)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    setup_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_period_months = models.IntegerField(default=1)
    service_description = models.TextField(blank=True)
    partner = models.CharField(max_length=100, blank=True, default='Main')
    vat_included = models.BooleanField(default=False)
    vat_name = models.CharField(max_length=100, blank=True)

    download_kbps = models.IntegerField(null=True, blank=True)
    upload_kbps = models.IntegerField(null=True, blank=True)
    guaranteed_speed = models.CharField(max_length=50, blank=True)
    priority = models.CharField(max_length=50, blank=True, default='Normal')
    aggregation_ratio = models.IntegerField(default=1)
    burst_profile = models.CharField(max_length=100, blank=True)

    transaction_category = models.CharField(max_length=100, blank=True)
    billing_cycle = models.CharField(max_length=20, choices=BillingCycleChoices, default=BillingCycleChoices.CYCLE_MONTHLY)
    activation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    activation_fee_when = models.CharField(max_length=100, blank=True, default='First service billing')
    contract_duration_months = models.IntegerField(default=1)
    automatic_renewal = models.BooleanField(default=True)
    auto_reactivate = models.BooleanField(default=False)
    cancellation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    prior_cancellation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_type = models.CharField(max_length=20, choices=DiscountTypeChoices, default=DiscountTypeChoices.TYPE_FIXED)

    show_tariff_customer_portal = models.BooleanField(default=True)
    hide_tariff_admin_portal = models.BooleanField(default=False)
    available_locations = models.CharField(max_length=255, blank=True)
    customer_category = models.CharField(max_length=100, blank=True)
    customer_labels = models.CharField(max_length=255, blank=True)
    available_upgrade_tariffs = models.CharField(max_length=255, blank=True)
    available_for_social_register = models.BooleanField(default=False)

    stripe_price_id = models.CharField(max_length=128, blank=True)
    description = models.TextField(blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)
        verbose_name = _('tariff plan')
        verbose_name_plural = _('tariff plans')

    def __str__(self):
        return self.name

    def get_status_color(self):
        return GenericStatusChoices.colors.get(self.status)

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:tariffplan', args=[self.pk])


class TariffBundle(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    status = models.CharField(max_length=50, choices=GenericStatusChoices, default=GenericStatusChoices.STATUS_ACTIVE)
    enabled = models.BooleanField(default=True)
    service_description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat_included = models.BooleanField(default=False)
    vat_name = models.CharField(max_length=100, blank=True)
    partner = models.CharField(max_length=100, blank=True, default='Main')
    billing_cycle = models.CharField(max_length=20, choices=BillingCycleChoices, default=BillingCycleChoices.CYCLE_MONTHLY)
    transaction_category = models.CharField(max_length=100, blank=True)
    activation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    contract_duration_months = models.IntegerField(default=1)
    automatic_renewal = models.BooleanField(default=True)
    auto_reactivate = models.BooleanField(default=False)
    cancellation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    prior_cancellation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_type = models.CharField(max_length=20, choices=DiscountTypeChoices, default=DiscountTypeChoices.TYPE_FIXED)
    show_tariff_customer_portal = models.BooleanField(default=True)
    hide_tariff_admin_portal = models.BooleanField(default=False)
    available_locations = models.CharField(max_length=255, blank=True)
    customer_category = models.CharField(max_length=100, blank=True)
    customer_labels = models.CharField(max_length=255, blank=True)
    included_tariffs = models.ManyToManyField(TariffPlan, related_name='bundles', blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)
        verbose_name = _('tariff bundle')
        verbose_name_plural = _('tariff bundles')

    def __str__(self):
        return self.name

    def get_status_color(self):
        return GenericStatusChoices.colors.get(self.status)

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:tariffbundle', args=[self.pk])


class BillingAccount(NetBoxModel):
    tenant = models.OneToOneField('tenancy.Tenant', on_delete=models.PROTECT, related_name='billing_account')
    status = models.CharField(max_length=50, choices=GenericStatusChoices, default=GenericStatusChoices.STATUS_ACTIVE)
    stripe_customer_id = models.CharField(max_length=128, blank=True)
    autopay_enabled = models.BooleanField(default=False)
    billing_email = models.EmailField(blank=True)
    billing_phone = models.CharField(max_length=50, blank=True)
    external_reference = models.CharField(max_length=100, blank=True)
    account_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    preferred_payment_method = models.CharField(max_length=30, choices=PaymentMethodChoices, default=PaymentMethodChoices.METHOD_CREDIT_CARD)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('tenant__name',)
        verbose_name = _('billing account')
        verbose_name_plural = _('billing accounts')

    def __str__(self):
        return str(self.tenant)

    def get_status_color(self):
        return GenericStatusChoices.colors.get(self.status)

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:billingaccount', args=[self.pk])


class CustomerLabel(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    color = ColorField(default='7952f2')
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)
        verbose_name = _('customer label')
        verbose_name_plural = _('customer labels')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:customerlabel', args=[self.pk])


class CustomerProfile(NetBoxModel):
    account = models.OneToOneField(BillingAccount, on_delete=models.CASCADE, related_name='profile')

    portal_login = models.CharField(max_length=100, blank=True)
    portal_password = models.CharField(max_length=255, blank=True)
    billing_type = models.CharField(max_length=20, choices=BillingTypeChoices, default=BillingTypeChoices.TYPE_RECURRING)
    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    billing_email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=50, blank=True)
    partner = models.CharField(max_length=100, blank=True, default='Main')
    location = models.CharField(max_length=100, blank=True)
    street = models.CharField(max_length=255, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state_province = models.CharField(max_length=100, blank=True)
    geodata = models.CharField(max_length=100, blank=True)
    date_added = models.DateField(default=date.today)

    category = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    identification = models.CharField(max_length=100, blank=True)
    preferred_payment = models.CharField(max_length=30, choices=PaymentMethodChoices, default=PaymentMethodChoices.METHOD_CREDIT_CARD)
    address = models.CharField(max_length=255, blank=True)
    unit_number = models.CharField(max_length=50, blank=True)
    last4_ssn = models.CharField(max_length=4, blank=True)
    preferred_installation_days = models.CharField(max_length=255, blank=True)
    tv_content_interest = models.CharField(max_length=50, blank=True)
    coverage_notes = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)
    network_device = models.ForeignKey('dcim.Device', on_delete=models.SET_NULL, related_name='customer_profiles', null=True, blank=True)

    labels = models.ManyToManyField(CustomerLabel, related_name='profiles', blank=True)

    class Meta:
        ordering = ('account__tenant__name',)
        verbose_name = _('customer profile')
        verbose_name_plural = _('customer profiles')

    def __str__(self):
        return f'Profile: {self.account.tenant}'

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:customerprofile', args=[self.pk])


class Subscription(NetBoxModel):
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name='subscriptions')
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='subscriptions', null=True, blank=True)
    tariff_plan = models.ForeignKey(TariffPlan, on_delete=models.PROTECT, related_name='subscriptions', null=True, blank=True)
    tariff_bundle = models.ForeignKey(TariffBundle, on_delete=models.PROTECT, related_name='subscriptions', null=True, blank=True)
    cpe_device = models.ForeignKey('dcim.Device', on_delete=models.PROTECT, related_name='billing_subscriptions', null=True, blank=True)

    service_login = models.CharField(max_length=100, blank=True)
    ipv4_address = models.GenericIPAddressField(blank=True, null=True, protocol='IPv4')

    status = models.CharField(max_length=50, choices=SubscriptionStatusChoices, default=SubscriptionStatusChoices.STATUS_ACTIVE)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    billing_start_date = models.DateField(null=True, blank=True)
    billing_end_date = models.DateField(null=True, blank=True)
    invoiced_until = models.DateField(null=True, blank=True)

    rule = models.CharField(max_length=100, blank=True)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    stripe_subscription_id = models.CharField(max_length=128, blank=True)
    stripe_price_id = models.CharField(max_length=128, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('-created',)
        verbose_name = _('subscription')
        verbose_name_plural = _('subscriptions')

    def __str__(self):
        service = self.tariff_plan.name if self.tariff_plan else (self.tariff_bundle.name if self.tariff_bundle else 'Service')
        return f'{self.account.tenant} - {service}'

    def get_status_color(self):
        return SubscriptionStatusChoices.colors.get(self.status)

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:subscription', args=[self.pk])


class Invoice(NetBoxModel):
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name='invoices')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, related_name='invoices', null=True, blank=True)
    number = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=50, choices=InvoiceStatusChoices, default=InvoiceStatusChoices.STATUS_DRAFT)
    date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, choices=CurrencyChoices, default=CurrencyChoices.CURRENCY_USD)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=30, choices=PaymentMethodChoices, default=PaymentMethodChoices.METHOD_CREDIT_CARD)
    stripe_invoice_id = models.CharField(max_length=128, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=128, blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('-date', '-created')
        verbose_name = _('invoice')
        verbose_name_plural = _('invoices')

    def __str__(self):
        return self.number

    def get_status_color(self):
        return InvoiceStatusChoices.colors.get(self.status)

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:invoice', args=[self.pk])


class InvoiceLine(NetBoxModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taxable = models.BooleanField(default=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('invoice', 'id')
        verbose_name = _('invoice line')
        verbose_name_plural = _('invoice lines')

    def __str__(self):
        return f'{self.invoice.number} - {self.description}'

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:invoiceline', args=[self.pk])


class Payment(NetBoxModel):
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, related_name='payments', null=True, blank=True)
    method = models.CharField(max_length=30, choices=PaymentMethodChoices, default=PaymentMethodChoices.METHOD_CREDIT_CARD)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_at = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('-paid_at', '-created')
        verbose_name = _('payment')
        verbose_name_plural = _('payments')

    def __str__(self):
        return f'{self.account.tenant} - {self.amount} {self.method}'

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:payment', args=[self.pk])


class ScheduledPayment(NetBoxModel):
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name='scheduled_payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, related_name='scheduled_payments', null=True, blank=True)
    method = models.CharField(max_length=30, choices=PaymentMethodChoices, default=PaymentMethodChoices.METHOD_CREDIT_CARD)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, choices=CurrencyChoices, default=CurrencyChoices.CURRENCY_USD)
    run_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=ScheduledPaymentStatusChoices,
        default=ScheduledPaymentStatusChoices.STATUS_SCHEDULED,
    )
    stripe_customer_id = models.CharField(max_length=128, blank=True)
    stripe_payment_method_id = models.CharField(max_length=128, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=128, blank=True)
    description = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    external_reference = models.CharField(max_length=128, blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('run_at', 'created')
        verbose_name = _('scheduled payment')
        verbose_name_plural = _('scheduled payments')

    def __str__(self):
        return f'{self.account.tenant} {self.amount} at {self.run_at}'

    def get_status_color(self):
        return ScheduledPaymentStatusChoices.colors.get(self.status)

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:scheduledpayment', args=[self.pk])


class CustomerDocument(NetBoxModel):
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=150)
    document_type = models.CharField(max_length=50, blank=True)
    document_url = models.URLField(blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ('title',)
        verbose_name = _('customer document')
        verbose_name_plural = _('customer documents')

    def __str__(self):
        return f'{self.account.tenant} - {self.title}'

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:customerdocument', args=[self.pk])


class CustomerCommunication(NetBoxModel):
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name='communications')
    channel = models.CharField(max_length=50, blank=True)
    subject = models.CharField(max_length=150, blank=True)
    message = models.TextField(blank=True)
    direction = models.CharField(max_length=20, blank=True, default='outbound')
    occurred_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-occurred_at', '-created')
        verbose_name = _('customer communication')
        verbose_name_plural = _('customer communications')

    def __str__(self):
        return f'{self.account.tenant} - {self.channel}'

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:customercommunication', args=[self.pk])


class CustomerNote(NetBoxModel):
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name='notes')
    title = models.CharField(max_length=150)
    note = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ('completed', 'due_date', 'title')
        verbose_name = _('customer note')
        verbose_name_plural = _('customer notes')

    def __str__(self):
        return f'{self.account.tenant} - {self.title}'

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:customernote', args=[self.pk])


class StripeWebhookEvent(NetBoxModel):
    event_id = models.CharField(max_length=128, unique=True)
    event_type = models.CharField(max_length=128)
    livemode = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    account = models.ForeignKey(BillingAccount, on_delete=models.SET_NULL, related_name='stripe_events', null=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, related_name='stripe_events', null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ('-created',)
        verbose_name = _('stripe webhook event')
        verbose_name_plural = _('stripe webhook events')

    def __str__(self):
        return self.event_id

    def get_absolute_url(self):
        return reverse('plugins:netbox_billing:stripewebhookevent', args=[self.pk])

