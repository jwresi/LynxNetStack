from datetime import date, timedelta
from decimal import Decimal

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from tenancy.models import Tenant

from netbox_billing.models import (
    BillingAccount,
    CustomerLabel,
    CustomerProfile,
    Invoice,
    InvoiceLine,
    Payment,
    Property,
    Subscription,
    TariffBundle,
    TariffPlan,
    Unit,
)

PREFIX = 'NBILL-DEMO'


def slugify(value):
    return value.lower().replace(' ', '-').replace('/', '-').replace('_', '-')


# Cleanup scoped demo rows
Payment.objects.filter(account__tenant__name__startswith=PREFIX).delete()
InvoiceLine.objects.filter(invoice__number__startswith=PREFIX).delete()
Invoice.objects.filter(number__startswith=PREFIX).delete()
Subscription.objects.filter(account__tenant__name__startswith=PREFIX).delete()
CustomerProfile.objects.filter(account__tenant__name__startswith=PREFIX).delete()
BillingAccount.objects.filter(tenant__name__startswith=PREFIX).delete()
Unit.objects.filter(property__name__startswith=PREFIX).delete()
Property.objects.filter(name__startswith=PREFIX).delete()
TariffBundle.objects.filter(name__startswith=PREFIX).delete()
TariffPlan.objects.filter(name__startswith=PREFIX).delete()
CustomerLabel.objects.filter(name__startswith=PREFIX).delete()
Device.objects.filter(name__startswith=PREFIX).delete()
DeviceType.objects.filter(model__startswith=PREFIX).delete()
DeviceRole.objects.filter(name__startswith=PREFIX).delete()
Manufacturer.objects.filter(name__startswith=PREFIX).delete()
Site.objects.filter(name__startswith=PREFIX).delete()
Tenant.objects.filter(name__startswith=PREFIX).delete()

# Infrastructure
site = Site.objects.create(name=f'{PREFIX} Uptown', slug=slugify(f'{PREFIX} Uptown'), status='active', physical_address='1180 East New York Ave, Brooklyn, NY 11212')
manufacturer = Manufacturer.objects.create(name=f'{PREFIX} Networks', slug=slugify(f'{PREFIX} Networks'))
role = DeviceRole.objects.create(name=f'{PREFIX} CPE', slug=slugify(f'{PREFIX} CPE'), color='03a9f4')
dtype = DeviceType.objects.create(manufacturer=manufacturer, model=f'{PREFIX} Router-1', slug=slugify(f'{PREFIX} Router-1'))
device = Device.objects.create(name=f'{PREFIX}-CPE-001', device_type=dtype, role=role, site=site, status='active', serial='CPE0001')

# Customer
tenant = Tenant.objects.create(name=f'{PREFIX} NYCHA1196EastNewYorkAve4D', slug=slugify(f'{PREFIX} NYCHA1196EastNewYorkAve4D'))
account = BillingAccount.objects.create(
    tenant=tenant,
    status='active',
    stripe_customer_id='cus_demo_nycha_001',
    autopay_enabled=True,
    billing_email='nycha.demo@example.net',
    billing_phone='929-575-8985',
    account_balance=Decimal('0.00'),
    preferred_payment_method='credit_card',
)

label = CustomerLabel.objects.create(name=f'{PREFIX} ACP', slug=slugify(f'{PREFIX} ACP'), color='7952f2')

profile = CustomerProfile.objects.create(
    account=account,
    portal_login='NYCHA1196EastNewYorkAve4D',
    portal_password='demo-pass',
    billing_type='recurring',
    full_name='NYCHA1196EastNewYorkAve4D',
    email='customer@example.net',
    billing_email='billing@example.net',
    phone_number='9295758985',
    partner='Main',
    location='NYCHA',
    street='1196 Ralph Ave Rehab',
    zip_code='11212',
    city='Brooklyn',
    state_province='NY',
    category='Individual',
    preferred_payment='credit_card',
    address='1196 Ralph Ave Rehab',
    unit_number='4D',
    coverage_notes='Red Interior',
    network_device=device,
)
profile.labels.add(label)

# Property and unit
prop = Property.objects.create(name=f'{PREFIX} 1196 East New York Ave', slug=slugify(f'{PREFIX} 1196 East New York Ave'), status='active', site=site, address='1196 East New York Ave, Brooklyn, NY')
unit = Unit.objects.create(property=prop, unit_number='4D', status='active', tenant=tenant, service_address='1196 East New York Ave, Unit 4D, Brooklyn, NY')

# Tariffs and bundle
internet = TariffPlan.objects.create(
    name=f'{PREFIX} Gold Plan P79',
    slug=slugify(f'{PREFIX} Gold Plan P79'),
    tariff_type='internet',
    status='active',
    enabled=True,
    monthly_price=Decimal('29.99'),
    service_description='100/100 Mbps Internet P79',
    download_kbps=100000,
    upload_kbps=100000,
    vat_included=True,
    vat_name='0% (Default 0.00%)',
    partner='Main',
    billing_cycle='monthly',
    transaction_category='Gold Plan',
    contract_duration_months=1,
    automatic_renewal=True,
    show_tariff_customer_portal=True,
    available_locations='Park79',
)

bundle = TariffBundle.objects.create(
    name=f'{PREFIX} Gold Bundle ACP',
    slug=slugify(f'{PREFIX} Gold Bundle ACP'),
    status='active',
    enabled=True,
    service_description='ACP Gold bundle',
    price=Decimal('30.00'),
    vat_included=True,
    partner='Main',
    billing_cycle='monthly',
    transaction_category='Gold Plan',
    contract_duration_months=1,
    automatic_renewal=True,
    show_tariff_customer_portal=True,
    available_locations='Park79,Cambridge',
)
bundle.included_tariffs.add(internet)

subscription = Subscription.objects.create(
    account=account,
    unit=unit,
    tariff_plan=internet,
    tariff_bundle=bundle,
    cpe_device=device,
    service_login='NYCHA1196EastNewYorkAve4D',
    ipv4_address='10.0.8.201',
    status='active',
    start_date=date.today() - timedelta(days=45),
    billing_start_date=date.today() - timedelta(days=30),
    invoiced_until=date.today(),
    rule='No rule',
)

invoice = Invoice.objects.create(
    account=account,
    subscription=subscription,
    number=f'{PREFIX}-INV-0001',
    status='paid',
    date=date.today() - timedelta(days=15),
    due_date=date.today() - timedelta(days=5),
    payment_date=date.today() - timedelta(days=4),
    period_start=date.today() - timedelta(days=30),
    period_end=date.today(),
    subtotal=Decimal('29.99'),
    tax=Decimal('0.00'),
    total=Decimal('29.99'),
    balance_due=Decimal('0.00'),
    payment_method='credit_card',
)

InvoiceLine.objects.create(invoice=invoice, description='100/100 Mbps Internet NYCHA Entertainment', quantity=1, unit_price=Decimal('29.99'), line_total=Decimal('29.99'))
Payment.objects.create(account=account, invoice=invoice, method='credit_card', amount=Decimal('29.99'), paid_at=date.today() - timedelta(days=4), reference='pi_demo_001')

print('Seed completed')
print(f'Account: {account}')
print(f'Profile: {profile}')
print(f'Subscription: {subscription}')
print(f'Invoice: {invoice.number}')
