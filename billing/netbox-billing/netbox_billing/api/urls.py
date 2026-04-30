from netbox.api.routers import NetBoxRouter

from . import views

app_name = 'netbox_billing'

router = NetBoxRouter()
router.register('accounts', views.BillingAccountViewSet)
router.register('profiles', views.CustomerProfileViewSet)
router.register('labels', views.CustomerLabelViewSet)
router.register('properties', views.PropertyViewSet)
router.register('units', views.UnitViewSet)
router.register('tariffs', views.TariffPlanViewSet)
router.register('bundles', views.TariffBundleViewSet)
router.register('subscriptions', views.SubscriptionViewSet)
router.register('invoices', views.InvoiceViewSet)
router.register('invoice-lines', views.InvoiceLineViewSet)
router.register('payments', views.PaymentViewSet)
router.register('scheduled-payments', views.ScheduledPaymentViewSet)
router.register('documents', views.CustomerDocumentViewSet)
router.register('communications', views.CustomerCommunicationViewSet)
router.register('notes', views.CustomerNoteViewSet)
router.register('stripe-events', views.StripeWebhookEventViewSet)

urlpatterns = router.urls
