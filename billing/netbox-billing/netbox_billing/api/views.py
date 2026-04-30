from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets, models
from . import serializers


class PropertyViewSet(NetBoxModelViewSet):
    queryset = models.Property.objects.prefetch_related('tags')
    serializer_class = serializers.PropertySerializer
    filterset_class = filtersets.PropertyFilterSet


class UnitViewSet(NetBoxModelViewSet):
    queryset = models.Unit.objects.prefetch_related('tags')
    serializer_class = serializers.UnitSerializer
    filterset_class = filtersets.UnitFilterSet


class TariffPlanViewSet(NetBoxModelViewSet):
    queryset = models.TariffPlan.objects.prefetch_related('tags')
    serializer_class = serializers.TariffPlanSerializer
    filterset_class = filtersets.TariffPlanFilterSet


class TariffBundleViewSet(NetBoxModelViewSet):
    queryset = models.TariffBundle.objects.prefetch_related('tags', 'included_tariffs')
    serializer_class = serializers.TariffBundleSerializer
    filterset_class = filtersets.TariffBundleFilterSet


class BillingAccountViewSet(NetBoxModelViewSet):
    queryset = models.BillingAccount.objects.prefetch_related('tags')
    serializer_class = serializers.BillingAccountSerializer
    filterset_class = filtersets.BillingAccountFilterSet


class CustomerLabelViewSet(NetBoxModelViewSet):
    queryset = models.CustomerLabel.objects.prefetch_related('tags')
    serializer_class = serializers.CustomerLabelSerializer
    filterset_class = filtersets.CustomerLabelFilterSet


class CustomerProfileViewSet(NetBoxModelViewSet):
    queryset = models.CustomerProfile.objects.prefetch_related('tags', 'labels')
    serializer_class = serializers.CustomerProfileSerializer
    filterset_class = filtersets.CustomerProfileFilterSet


class SubscriptionViewSet(NetBoxModelViewSet):
    queryset = models.Subscription.objects.prefetch_related('tags')
    serializer_class = serializers.SubscriptionSerializer
    filterset_class = filtersets.SubscriptionFilterSet


class InvoiceViewSet(NetBoxModelViewSet):
    queryset = models.Invoice.objects.prefetch_related('tags')
    serializer_class = serializers.InvoiceSerializer
    filterset_class = filtersets.InvoiceFilterSet


class InvoiceLineViewSet(NetBoxModelViewSet):
    queryset = models.InvoiceLine.objects.prefetch_related('tags')
    serializer_class = serializers.InvoiceLineSerializer
    filterset_class = filtersets.InvoiceLineFilterSet


class PaymentViewSet(NetBoxModelViewSet):
    queryset = models.Payment.objects.prefetch_related('tags')
    serializer_class = serializers.PaymentSerializer
    filterset_class = filtersets.PaymentFilterSet


class ScheduledPaymentViewSet(NetBoxModelViewSet):
    queryset = models.ScheduledPayment.objects.prefetch_related('tags')
    serializer_class = serializers.ScheduledPaymentSerializer
    filterset_class = filtersets.ScheduledPaymentFilterSet


class CustomerDocumentViewSet(NetBoxModelViewSet):
    queryset = models.CustomerDocument.objects.prefetch_related('tags')
    serializer_class = serializers.CustomerDocumentSerializer
    filterset_class = filtersets.CustomerDocumentFilterSet


class CustomerCommunicationViewSet(NetBoxModelViewSet):
    queryset = models.CustomerCommunication.objects.prefetch_related('tags')
    serializer_class = serializers.CustomerCommunicationSerializer
    filterset_class = filtersets.CustomerCommunicationFilterSet


class CustomerNoteViewSet(NetBoxModelViewSet):
    queryset = models.CustomerNote.objects.prefetch_related('tags')
    serializer_class = serializers.CustomerNoteSerializer
    filterset_class = filtersets.CustomerNoteFilterSet


class StripeWebhookEventViewSet(NetBoxModelViewSet):
    queryset = models.StripeWebhookEvent.objects.prefetch_related('tags')
    serializer_class = serializers.StripeWebhookEventSerializer
    filterset_class = filtersets.StripeWebhookEventFilterSet
