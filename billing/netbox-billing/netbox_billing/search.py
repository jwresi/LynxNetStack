from netbox.search import SearchIndex, register_search

from .models import (
    BillingAccount,
    CustomerProfile,
    Invoice,
    Property,
    Subscription,
    TariffBundle,
    TariffPlan,
    Unit,
)


@register_search
class BillingSearchIndex(SearchIndex):
    model = BillingAccount
    fields = (('tenant', 100), ('stripe_customer_id', 200), ('billing_email', 300), ('billing_phone', 400))


@register_search
class CustomerProfileSearchIndex(SearchIndex):
    model = CustomerProfile
    fields = (
        ('full_name', 100),
        ('email', 200),
        ('phone_number', 300),
        ('address', 400),
        ('unit_number', 500),
    )


@register_search
class TariffSearchIndex(SearchIndex):
    model = TariffPlan
    fields = (('name', 100), ('slug', 200), ('service_description', 300), ('stripe_price_id', 400))


@register_search
class TariffBundleSearchIndex(SearchIndex):
    model = TariffBundle
    fields = (('name', 100), ('slug', 200), ('service_description', 300))


@register_search
class PropertySearchIndex(SearchIndex):
    model = Property
    fields = (('name', 100), ('slug', 200), ('address', 300))


@register_search
class UnitSearchIndex(SearchIndex):
    model = Unit
    fields = (('unit_number', 100), ('service_address', 200), ('property', 300), ('tenant', 400))


@register_search
class SubscriptionSearchIndex(SearchIndex):
    model = Subscription
    fields = (
        ('service_login', 100),
        ('ipv4_address', 200),
        ('stripe_subscription_id', 300),
        ('account', 400),
    )


@register_search
class InvoiceSearchIndex(SearchIndex):
    model = Invoice
    fields = (('number', 100), ('stripe_invoice_id', 200), ('account', 300))
