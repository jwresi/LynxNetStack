from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from .. import models


class PropertySerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:property-detail')

    class Meta:
        model = models.Property
        fields = ('id', 'url', 'display', 'name', 'slug', 'status', 'site', 'address', 'comments', 'tags', 'custom_fields', 'created', 'last_updated')


class UnitSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:unit-detail')

    class Meta:
        model = models.Unit
        fields = ('id', 'url', 'display', 'property', 'unit_number', 'floor', 'status', 'tenant', 'service_address', 'comments', 'tags', 'custom_fields', 'created', 'last_updated')


class TariffPlanSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:tariffplan-detail')

    class Meta:
        model = models.TariffPlan
        fields = '__all__'


class TariffBundleSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:tariffbundle-detail')

    class Meta:
        model = models.TariffBundle
        fields = '__all__'


class BillingAccountSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:billingaccount-detail')

    class Meta:
        model = models.BillingAccount
        fields = '__all__'


class CustomerLabelSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:customerlabel-detail')

    class Meta:
        model = models.CustomerLabel
        fields = '__all__'


class CustomerProfileSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:customerprofile-detail')

    class Meta:
        model = models.CustomerProfile
        fields = '__all__'


class SubscriptionSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:subscription-detail')

    class Meta:
        model = models.Subscription
        fields = '__all__'


class InvoiceSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:invoice-detail')

    class Meta:
        model = models.Invoice
        fields = '__all__'


class InvoiceLineSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:invoiceline-detail')

    class Meta:
        model = models.InvoiceLine
        fields = '__all__'


class PaymentSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:payment-detail')

    class Meta:
        model = models.Payment
        fields = '__all__'


class ScheduledPaymentSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:scheduledpayment-detail')

    class Meta:
        model = models.ScheduledPayment
        fields = '__all__'


class CustomerDocumentSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:customerdocument-detail')

    class Meta:
        model = models.CustomerDocument
        fields = '__all__'


class CustomerCommunicationSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:customercommunication-detail')

    class Meta:
        model = models.CustomerCommunication
        fields = '__all__'


class CustomerNoteSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:customernote-detail')

    class Meta:
        model = models.CustomerNote
        fields = '__all__'


class StripeWebhookEventSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_billing-api:stripewebhookevent-detail')

    class Meta:
        model = models.StripeWebhookEvent
        fields = '__all__'
