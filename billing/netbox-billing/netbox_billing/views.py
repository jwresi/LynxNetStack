from collections import OrderedDict
from datetime import datetime
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from netbox.views import generic
from tenancy import forms as tenancy_forms
from tenancy import models as tenancy_models
from users.models import User

from . import filtersets, forms, models, services, tables


CX_MODEL_CONFIG = {
    'tenant': {'queryset': tenancy_models.Tenant.objects.all(), 'form': tenancy_forms.TenantForm, 'catalog_tab': None},
    'billingaccount': {'queryset': models.BillingAccount.objects.all(), 'form': forms.BillingAccountForm, 'catalog_tab': None},
    'customerprofile': {'queryset': models.CustomerProfile.objects.all(), 'form': forms.CustomerProfileForm, 'catalog_tab': None},
    'subscription': {'queryset': models.Subscription.objects.all(), 'form': forms.SubscriptionForm, 'catalog_tab': 'services'},
    'invoice': {'queryset': models.Invoice.objects.all(), 'form': forms.InvoiceForm, 'catalog_tab': None},
    'payment': {'queryset': models.Payment.objects.all(), 'form': forms.PaymentForm, 'catalog_tab': None},
    'scheduledpayment': {'queryset': models.ScheduledPayment.objects.all(), 'form': forms.ScheduledPaymentForm, 'catalog_tab': None},
    'customerdocument': {'queryset': models.CustomerDocument.objects.all(), 'form': forms.CustomerDocumentForm, 'catalog_tab': None},
    'customercommunication': {'queryset': models.CustomerCommunication.objects.all(), 'form': forms.CustomerCommunicationForm, 'catalog_tab': None},
    'customernote': {'queryset': models.CustomerNote.objects.all(), 'form': forms.CustomerNoteForm, 'catalog_tab': None},
    'tariffplan': {'queryset': models.TariffPlan.objects.all(), 'form': forms.TariffPlanForm, 'catalog_tab': 'plans'},
    'tariffbundle': {'queryset': models.TariffBundle.objects.all(), 'form': forms.TariffBundleForm, 'catalog_tab': 'bundles'},
    'property': {'queryset': models.Property.objects.all(), 'form': forms.PropertyForm, 'catalog_tab': 'services'},
    'unit': {'queryset': models.Unit.objects.all(), 'form': forms.UnitForm, 'catalog_tab': 'services'},
}


def _cx_groups():
    cfg = settings.PLUGINS_CONFIG.get('netbox_billing', {})
    groups = cfg.get('cx_groups', ['cx', 'customer_experience', 'csr'])
    return {str(name).strip().lower() for name in groups}


def _is_cx_user(user):
    if not user.is_authenticated:
        return False
    user_groups = {g.name.lower() for g in user.groups.all()}
    return bool(user_groups.intersection(_cx_groups()))


def _prefer_cx_ui(request):
    return _is_cx_user(request.user) and request.GET.get('eng') != '1'


def _ticket_model():
    try:
        return apps.get_model('netbox_ticketing', 'ServiceTicket')
    except LookupError:
        return None


def _account_context(request, instance):
    active_tab = request.GET.get('tab', 'information')
    subscriptions = models.Subscription.objects.filter(account=instance).select_related(
        'tariff_plan', 'tariff_bundle', 'cpe_device', 'unit'
    )
    invoices = models.Invoice.objects.filter(account=instance).select_related('subscription').order_by('-date', '-created')
    payments = models.Payment.objects.filter(account=instance).select_related('invoice').order_by('-paid_at', '-created')
    scheduled_payments = models.ScheduledPayment.objects.filter(account=instance).select_related('invoice').order_by('run_at', 'created')

    subscriptions_table = tables.SubscriptionTable(subscriptions)
    subscriptions_table.configure(request)

    invoices_table = tables.InvoiceTable(invoices)
    invoices_table.configure(request)

    payments_table = tables.PaymentTable(payments)
    payments_table.configure(request)

    scheduled_payments_table = tables.ScheduledPaymentTable(scheduled_payments)
    scheduled_payments_table.configure(request)

    documents_table = tables.CustomerDocumentTable(instance.documents.all())
    documents_table.configure(request)

    communications_table = tables.CustomerCommunicationTable(instance.communications.all())
    communications_table.configure(request)

    notes_table = tables.CustomerNoteTable(instance.notes.all())
    notes_table.configure(request)

    tickets = []
    ticket_model = _ticket_model()
    if ticket_model:
        tickets = ticket_model.objects.filter(account=instance).select_related(
            'subscription', 'opened_by', 'assigned_to'
        ).order_by('-created')

    profile = getattr(instance, 'profile', None)

    total_invoiced = sum((invoice.total or Decimal('0')) for invoice in invoices)
    total_paid = sum((payment.amount or Decimal('0')) for payment in payments)

    invoice_totals_by_status = OrderedDict()
    for status_key, status_label, _ in models.InvoiceStatusChoices.CHOICES:
        scoped = invoices.filter(status=status_key)
        invoice_totals_by_status[status_label] = {
            'count': scoped.count(),
            'total': sum((item.total or Decimal('0')) for item in scoped),
        }

    paid_totals_by_method = OrderedDict()
    for method_key, method_label in models.PaymentMethodChoices.CHOICES:
        scoped = payments.filter(method=method_key)
        paid_totals_by_method[method_label] = {
            'count': scoped.count(),
            'total': sum((item.amount or Decimal('0')) for item in scoped),
        }

    return {
        'active_tab': active_tab,
        'profile': profile,
        'subscriptions': subscriptions,
        'invoices': invoices,
        'payments': payments,
        'scheduled_payments': scheduled_payments,
        'documents': instance.documents.all(),
        'communications': instance.communications.all(),
        'notes': instance.notes.all(),
        'tickets': tickets,
        'subscriptions_table': subscriptions_table,
        'invoices_table': invoices_table,
        'payments_table': payments_table,
        'scheduled_payments_table': scheduled_payments_table,
        'documents_table': documents_table,
        'communications_table': communications_table,
        'notes_table': notes_table,
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'invoice_totals_by_status': invoice_totals_by_status,
        'paid_totals_by_method': paid_totals_by_method,
    }


def _cx_config_or_404(model_key):
    config = CX_MODEL_CONFIG.get(model_key)
    if not config:
        raise PermissionDenied(f'Unsupported CX model: {model_key}')
    return config


def _require_model_permission(request, model_class, action):
    codename = f'{model_class._meta.app_label}.{action}_{model_class._meta.model_name}'
    if not request.user.has_perm(codename):
        raise PermissionDenied(f'Missing permission: {codename}')


def _cx_default_redirect(saved_object):
    if isinstance(saved_object, models.BillingAccount):
        return reverse('plugins:netbox_billing:cx_customer', kwargs={'pk': saved_object.pk})

    account_id = getattr(saved_object, 'account_id', None)
    if account_id:
        return f"{reverse('plugins:netbox_billing:cx_customer', kwargs={'pk': account_id})}?tab=billing"
    return reverse('plugins:netbox_billing:cx_dashboard')


def _cx_delete_redirect(model_key):
    catalog_tab = CX_MODEL_CONFIG[model_key].get('catalog_tab')
    if catalog_tab:
        return f"{reverse('plugins:netbox_billing:cx_catalog')}?tab={catalog_tab}"
    return reverse('plugins:netbox_billing:cx_dashboard')


class CXObjectEditView(View):
    template_name = 'netbox_billing/cx_form.html'

    def get(self, request, model, pk=None):
        config = _cx_config_or_404(model)
        form_class = config['form']
        queryset = config['queryset']
        model_class = queryset.model
        action = 'change' if pk else 'add'
        _require_model_permission(request, model_class, action)

        instance = get_object_or_404(queryset, pk=pk) if pk else None
        initial = {}
        for key in ('account', 'invoice', 'subscription', 'property', 'tenant'):
            value = request.GET.get(key)
            if value:
                initial[key] = value

        form = form_class(instance=instance, initial=initial)
        context = {
            'form': form,
            'mode': 'edit' if pk else 'add',
            'model_key': model,
            'object_name': model_class._meta.verbose_name.title(),
            'next_url': request.GET.get('next', ''),
        }
        return render(request, self.template_name, context)

    def post(self, request, model, pk=None):
        config = _cx_config_or_404(model)
        form_class = config['form']
        queryset = config['queryset']
        model_class = queryset.model
        action = 'change' if pk else 'add'
        _require_model_permission(request, model_class, action)

        instance = get_object_or_404(queryset, pk=pk) if pk else None
        form = form_class(request.POST, request.FILES, instance=instance)
        next_url = request.POST.get('next', '').strip()
        if form.is_valid():
            saved = form.save()
            messages.success(request, f'{model_class._meta.verbose_name.title()} saved.')
            return redirect(next_url or _cx_default_redirect(saved))

        context = {
            'form': form,
            'mode': 'edit' if pk else 'add',
            'model_key': model,
            'object_name': model_class._meta.verbose_name.title(),
            'next_url': next_url,
        }
        return render(request, self.template_name, context)


class CXObjectDeleteView(View):
    template_name = 'netbox_billing/cx_confirm_delete.html'

    def get(self, request, model, pk):
        config = _cx_config_or_404(model)
        queryset = config['queryset']
        model_class = queryset.model
        _require_model_permission(request, model_class, 'delete')
        obj = get_object_or_404(queryset, pk=pk)
        return render(
            request,
            self.template_name,
            {
                'model_key': model,
                'object_name': model_class._meta.verbose_name.title(),
                'object_repr': str(obj),
                'next_url': request.GET.get('next', ''),
            },
        )

    def post(self, request, model, pk):
        config = _cx_config_or_404(model)
        queryset = config['queryset']
        model_class = queryset.model
        _require_model_permission(request, model_class, 'delete')
        obj = get_object_or_404(queryset, pk=pk)
        next_url = request.POST.get('next', '').strip()
        obj.delete()
        messages.success(request, f'{model_class._meta.verbose_name.title()} deleted.')
        return redirect(next_url or _cx_delete_redirect(model))


class PropertyView(generic.ObjectView):
    queryset = models.Property.objects.all()


class PropertyListView(generic.ObjectListView):
    queryset = models.Property.objects.all()
    table = tables.PropertyTable
    filterset = filtersets.PropertyFilterSet


class PropertyEditView(generic.ObjectEditView):
    queryset = models.Property.objects.all()
    form = forms.PropertyForm


class PropertyDeleteView(generic.ObjectDeleteView):
    queryset = models.Property.objects.all()


class UnitView(generic.ObjectView):
    queryset = models.Unit.objects.select_related('property', 'tenant')


class UnitListView(generic.ObjectListView):
    queryset = models.Unit.objects.select_related('property', 'tenant')
    table = tables.UnitTable
    filterset = filtersets.UnitFilterSet


class UnitEditView(generic.ObjectEditView):
    queryset = models.Unit.objects.all()
    form = forms.UnitForm


class UnitDeleteView(generic.ObjectDeleteView):
    queryset = models.Unit.objects.all()


class TariffPlanView(generic.ObjectView):
    queryset = models.TariffPlan.objects.all()


class TariffPlanListView(generic.ObjectListView):
    queryset = models.TariffPlan.objects.all()
    table = tables.TariffPlanTable
    filterset = filtersets.TariffPlanFilterSet


class TariffPlanEditView(generic.ObjectEditView):
    queryset = models.TariffPlan.objects.all()
    form = forms.TariffPlanForm


class TariffPlanDeleteView(generic.ObjectDeleteView):
    queryset = models.TariffPlan.objects.all()


class TariffBundleView(generic.ObjectView):
    queryset = models.TariffBundle.objects.prefetch_related('included_tariffs')


class TariffBundleListView(generic.ObjectListView):
    queryset = models.TariffBundle.objects.prefetch_related('included_tariffs')
    table = tables.TariffBundleTable
    filterset = filtersets.TariffBundleFilterSet


class TariffBundleEditView(generic.ObjectEditView):
    queryset = models.TariffBundle.objects.all()
    form = forms.TariffBundleForm


class TariffBundleDeleteView(generic.ObjectDeleteView):
    queryset = models.TariffBundle.objects.all()


class BillingAccountView(generic.ObjectView):
    queryset = models.BillingAccount.objects.select_related('tenant', 'profile')

    def dispatch(self, request, *args, **kwargs):
        if _prefer_cx_ui(request):
            return redirect('plugins:netbox_billing:cx_customer', pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_extra_context(self, request, instance):
        return _account_context(request, instance)


class BillingAccountListView(generic.ObjectListView):
    queryset = models.BillingAccount.objects.select_related('tenant')
    table = tables.BillingAccountTable
    filterset = filtersets.BillingAccountFilterSet

    def dispatch(self, request, *args, **kwargs):
        if _prefer_cx_ui(request):
            return redirect('plugins:netbox_billing:cx_dashboard')
        return super().dispatch(request, *args, **kwargs)


class BillingAccountEditView(generic.ObjectEditView):
    queryset = models.BillingAccount.objects.all()
    form = forms.BillingAccountForm


class BillingAccountDeleteView(generic.ObjectDeleteView):
    queryset = models.BillingAccount.objects.all()


class CustomerLabelView(generic.ObjectView):
    queryset = models.CustomerLabel.objects.all()


class CustomerLabelListView(generic.ObjectListView):
    queryset = models.CustomerLabel.objects.all()
    table = tables.CustomerLabelTable
    filterset = filtersets.CustomerLabelFilterSet


class CustomerLabelEditView(generic.ObjectEditView):
    queryset = models.CustomerLabel.objects.all()
    form = forms.CustomerLabelForm


class CustomerLabelDeleteView(generic.ObjectDeleteView):
    queryset = models.CustomerLabel.objects.all()


class CustomerProfileView(generic.ObjectView):
    queryset = models.CustomerProfile.objects.select_related('account', 'network_device')


class CustomerProfileListView(generic.ObjectListView):
    queryset = models.CustomerProfile.objects.select_related('account', 'network_device')
    table = tables.CustomerProfileTable
    filterset = filtersets.CustomerProfileFilterSet


class CustomerProfileEditView(generic.ObjectEditView):
    queryset = models.CustomerProfile.objects.all()
    form = forms.CustomerProfileForm


class CustomerProfileDeleteView(generic.ObjectDeleteView):
    queryset = models.CustomerProfile.objects.all()


class SubscriptionView(generic.ObjectView):
    queryset = models.Subscription.objects.select_related('account', 'tariff_plan', 'tariff_bundle', 'unit', 'cpe_device')


class SubscriptionListView(generic.ObjectListView):
    queryset = models.Subscription.objects.select_related('account', 'tariff_plan', 'tariff_bundle', 'unit', 'cpe_device')
    table = tables.SubscriptionTable
    filterset = filtersets.SubscriptionFilterSet


class SubscriptionEditView(generic.ObjectEditView):
    queryset = models.Subscription.objects.all()
    form = forms.SubscriptionForm


class SubscriptionDeleteView(generic.ObjectDeleteView):
    queryset = models.Subscription.objects.all()


class InvoiceView(generic.ObjectView):
    queryset = models.Invoice.objects.select_related('account', 'subscription')


class InvoiceListView(generic.ObjectListView):
    queryset = models.Invoice.objects.select_related('account', 'subscription')
    table = tables.InvoiceTable
    filterset = filtersets.InvoiceFilterSet


class InvoiceEditView(generic.ObjectEditView):
    queryset = models.Invoice.objects.all()
    form = forms.InvoiceForm


class InvoiceDeleteView(generic.ObjectDeleteView):
    queryset = models.Invoice.objects.all()


class InvoiceLineView(generic.ObjectView):
    queryset = models.InvoiceLine.objects.select_related('invoice')


class InvoiceLineListView(generic.ObjectListView):
    queryset = models.InvoiceLine.objects.select_related('invoice')
    table = tables.InvoiceLineTable
    filterset = filtersets.InvoiceLineFilterSet


class InvoiceLineEditView(generic.ObjectEditView):
    queryset = models.InvoiceLine.objects.all()
    form = forms.InvoiceLineForm


class InvoiceLineDeleteView(generic.ObjectDeleteView):
    queryset = models.InvoiceLine.objects.all()


class PaymentView(generic.ObjectView):
    queryset = models.Payment.objects.select_related('account', 'invoice')


class PaymentListView(generic.ObjectListView):
    queryset = models.Payment.objects.select_related('account', 'invoice')
    table = tables.PaymentTable
    filterset = filtersets.PaymentFilterSet


class PaymentEditView(generic.ObjectEditView):
    queryset = models.Payment.objects.all()
    form = forms.PaymentForm


class PaymentDeleteView(generic.ObjectDeleteView):
    queryset = models.Payment.objects.all()


class ScheduledPaymentView(generic.ObjectView):
    queryset = models.ScheduledPayment.objects.select_related('account', 'invoice')


class ScheduledPaymentListView(generic.ObjectListView):
    queryset = models.ScheduledPayment.objects.select_related('account', 'invoice')
    table = tables.ScheduledPaymentTable
    filterset = filtersets.ScheduledPaymentFilterSet


class ScheduledPaymentEditView(generic.ObjectEditView):
    queryset = models.ScheduledPayment.objects.all()
    form = forms.ScheduledPaymentForm


class ScheduledPaymentDeleteView(generic.ObjectDeleteView):
    queryset = models.ScheduledPayment.objects.all()


class CustomerDocumentView(generic.ObjectView):
    queryset = models.CustomerDocument.objects.select_related('account')


class CustomerDocumentListView(generic.ObjectListView):
    queryset = models.CustomerDocument.objects.select_related('account')
    table = tables.CustomerDocumentTable
    filterset = filtersets.CustomerDocumentFilterSet


class CustomerDocumentEditView(generic.ObjectEditView):
    queryset = models.CustomerDocument.objects.all()
    form = forms.CustomerDocumentForm


class CustomerDocumentDeleteView(generic.ObjectDeleteView):
    queryset = models.CustomerDocument.objects.all()


class CustomerCommunicationView(generic.ObjectView):
    queryset = models.CustomerCommunication.objects.select_related('account')


class CustomerCommunicationListView(generic.ObjectListView):
    queryset = models.CustomerCommunication.objects.select_related('account')
    table = tables.CustomerCommunicationTable
    filterset = filtersets.CustomerCommunicationFilterSet


class CustomerCommunicationEditView(generic.ObjectEditView):
    queryset = models.CustomerCommunication.objects.all()
    form = forms.CustomerCommunicationForm


class CustomerCommunicationDeleteView(generic.ObjectDeleteView):
    queryset = models.CustomerCommunication.objects.all()


class CustomerNoteView(generic.ObjectView):
    queryset = models.CustomerNote.objects.select_related('account')


class CustomerNoteListView(generic.ObjectListView):
    queryset = models.CustomerNote.objects.select_related('account')
    table = tables.CustomerNoteTable
    filterset = filtersets.CustomerNoteFilterSet


class CustomerNoteEditView(generic.ObjectEditView):
    queryset = models.CustomerNote.objects.all()
    form = forms.CustomerNoteForm


class CustomerNoteDeleteView(generic.ObjectDeleteView):
    queryset = models.CustomerNote.objects.all()


class StripeWebhookEventView(generic.ObjectView):
    queryset = models.StripeWebhookEvent.objects.select_related('account', 'invoice')


class StripeWebhookEventListView(generic.ObjectListView):
    queryset = models.StripeWebhookEvent.objects.select_related('account', 'invoice')
    table = tables.StripeWebhookEventTable
    filterset = filtersets.StripeWebhookEventFilterSet


class StripeWebhookEventEditView(generic.ObjectEditView):
    queryset = models.StripeWebhookEvent.objects.all()
    form = forms.StripeWebhookEventForm


class StripeWebhookEventDeleteView(generic.ObjectDeleteView):
    queryset = models.StripeWebhookEvent.objects.all()


class CXDashboardView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.view_billingaccount'
    template_name = 'netbox_billing/cx_dashboard.html'

    def get(self, request):
        q = (request.GET.get('q') or '').strip()
        status_filter = (request.GET.get('status') or '').strip().lower()
        accounts = models.BillingAccount.objects.select_related('tenant', 'profile').prefetch_related(
            'subscriptions__tariff_plan', 'subscriptions__tariff_bundle'
        )
        if q:
            accounts = accounts.filter(
                Q(tenant__name__icontains=q)
                | Q(profile__full_name__icontains=q)
                | Q(profile__portal_login__icontains=q)
            )
        if status_filter in {'active', 'inactive'}:
            accounts = accounts.filter(status=status_filter)
        accounts = accounts.order_by('tenant__name')[:250]

        account_rows = []
        for account in accounts:
            active_services = account.subscriptions.filter(status='active')
            mrr = Decimal('0')
            for service in active_services:
                if service.price_override:
                    mrr += service.price_override
                elif service.tariff_plan:
                    mrr += service.tariff_plan.monthly_price
                elif service.tariff_bundle:
                    mrr += service.tariff_bundle.price
            account_rows.append(
                {
                    'account': account,
                    'profile': getattr(account, 'profile', None),
                    'active_services': active_services.count(),
                    'cpe_count': active_services.exclude(cpe_device__isnull=True).count(),
                    'mrr': mrr,
                }
            )
        ticket_model = _ticket_model()

        context = {
            'q': q,
            'status_filter': status_filter,
            'account_rows': account_rows,
            'customer_count': len(account_rows),
            'total_mrr': sum((row['mrr'] for row in account_rows), Decimal('0')),
            'total_balance': sum((row['account'].account_balance for row in account_rows), Decimal('0')),
            'open_ticket_count': ticket_model.objects.exclude(status__in=['resolved', 'closed']).count() if ticket_model else 0,
        }
        return render(request, self.template_name, context)


class CXCatalogView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.view_tariffplan'
    template_name = 'netbox_billing/cx_catalog.html'

    def get(self, request):
        active_tab = (request.GET.get('tab') or 'plans').strip()
        plans = models.TariffPlan.objects.all().order_by('name')
        bundles = models.TariffBundle.objects.prefetch_related('included_tariffs').order_by('name')
        services = models.Subscription.objects.select_related(
            'account__tenant', 'tariff_plan', 'tariff_bundle', 'unit', 'cpe_device'
        ).order_by('-created')[:250]

        context = {
            'active_tab': active_tab,
            'plans': plans,
            'bundles': bundles,
            'services': services,
        }
        return render(request, self.template_name, context)


class CXOnboardingView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.add_billingaccount'
    template_name = 'netbox_billing/cx_onboarding.html'

    def get(self, request):
        latest_accounts = models.BillingAccount.objects.select_related('tenant').order_by('-created')[:20]
        latest_subscriptions = models.Subscription.objects.select_related('account__tenant', 'cpe_device').order_by('-created')[:20]
        context = {
            'latest_accounts': latest_accounts,
            'latest_subscriptions': latest_subscriptions,
        }
        return render(request, self.template_name, context)


class CXCustomerView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.view_billingaccount'
    template_name = 'netbox_billing/cx_customer.html'

    def get(self, request, pk):
        account = get_object_or_404(models.BillingAccount.objects.select_related('tenant', 'profile'), pk=pk)
        context = {'object': account, **_account_context(request, account)}
        return render(request, self.template_name, context)


class CXSchedulePaymentView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.change_billingaccount'

    def post(self, request, pk):
        account = get_object_or_404(models.BillingAccount, pk=pk)
        amount_raw = (request.POST.get('amount') or '').strip()
        run_at_raw = (request.POST.get('run_at') or '').strip()
        method = (request.POST.get('method') or models.PaymentMethodChoices.METHOD_CREDIT_CARD).strip()
        currency = (request.POST.get('currency') or models.CurrencyChoices.CURRENCY_USD).strip().lower()
        description = (request.POST.get('description') or '').strip()
        stripe_customer_id = (request.POST.get('stripe_customer_id') or account.stripe_customer_id or '').strip()
        stripe_payment_method_id = (request.POST.get('stripe_payment_method_id') or '').strip()
        invoice_id = request.POST.get('invoice_id')

        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                raise ValueError('Amount must be greater than zero.')
            run_at = datetime.fromisoformat(run_at_raw)
            if timezone.is_naive(run_at):
                run_at = timezone.make_aware(run_at, timezone.get_current_timezone())
        except Exception as exc:
            messages.error(request, f'Invalid schedule request: {exc}')
            return redirect(f"{account.get_absolute_url()}?tab=billing")

        invoice = None
        if invoice_id:
            invoice = models.Invoice.objects.filter(pk=invoice_id, account=account).first()

        models.ScheduledPayment.objects.create(
            account=account,
            invoice=invoice,
            method=method,
            amount=amount,
            currency=currency,
            run_at=run_at,
            stripe_customer_id=stripe_customer_id,
            stripe_payment_method_id=stripe_payment_method_id,
            description=description,
        )
        messages.success(request, f'Scheduled payment of {amount} for {run_at}.')
        return redirect(f"{account.get_absolute_url()}?tab=billing")


class CXRunScheduledPaymentView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.change_billingaccount'

    def post(self, request, pk, scheduled_payment_pk):
        account = get_object_or_404(models.BillingAccount, pk=pk)
        scheduled = get_object_or_404(models.ScheduledPayment, pk=scheduled_payment_pk, account=account)
        ok, detail = services.process_scheduled_payment(scheduled)
        if ok:
            messages.success(request, f'Scheduled payment processed: {detail}')
        else:
            messages.error(request, f'Scheduled payment failed: {detail}')
        return redirect(f"{account.get_absolute_url()}?tab=billing")


class CXCancelScheduledPaymentView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.change_billingaccount'

    def post(self, request, pk, scheduled_payment_pk):
        account = get_object_or_404(models.BillingAccount, pk=pk)
        scheduled = get_object_or_404(models.ScheduledPayment, pk=scheduled_payment_pk, account=account)
        if scheduled.status == models.ScheduledPaymentStatusChoices.STATUS_SUCCEEDED:
            messages.error(request, 'Cannot cancel a successful scheduled payment.')
            return redirect(f"{account.get_absolute_url()}?tab=billing")

        scheduled.status = models.ScheduledPaymentStatusChoices.STATUS_CANCELED
        scheduled.canceled_at = timezone.now()
        scheduled.save()
        messages.success(request, 'Scheduled payment canceled.')
        return redirect(f"{account.get_absolute_url()}?tab=billing")


class CXChargeNowView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.change_billingaccount'

    def post(self, request, pk):
        account = get_object_or_404(models.BillingAccount, pk=pk)
        amount_raw = (request.POST.get('amount') or '').strip()
        method = (request.POST.get('method') or models.PaymentMethodChoices.METHOD_CREDIT_CARD).strip()
        currency = (request.POST.get('currency') or models.CurrencyChoices.CURRENCY_USD).strip().lower()
        description = (request.POST.get('description') or f'Immediate charge for account {account.pk}').strip()
        stripe_payment_method_id = (request.POST.get('stripe_payment_method_id') or '').strip()
        customer_id = (request.POST.get('stripe_customer_id') or account.stripe_customer_id or '').strip()
        invoice_id = request.POST.get('invoice_id')

        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                raise ValueError('Amount must be greater than zero.')
        except Exception as exc:
            messages.error(request, f'Invalid amount: {exc}')
            return redirect(f"{account.get_absolute_url()}?tab=billing")

        invoice = None
        if invoice_id:
            invoice = models.Invoice.objects.filter(pk=invoice_id, account=account).first()

        try:
            intent = services.create_payment_intent(
                amount=amount,
                currency=currency,
                customer_id=customer_id,
                payment_method_id=stripe_payment_method_id,
                description=description,
                metadata={
                    'billing_account_id': str(account.pk),
                    'invoice_id': str(invoice.pk) if invoice else '',
                    'mode': 'manual_charge',
                },
            )
            services.record_successful_payment(
                account=account,
                invoice=invoice,
                method=method,
                amount=amount,
                reference=intent.id,
                comments='Created from CX immediate Stripe charge.',
            )
            messages.success(request, f'Charge succeeded: {intent.id}')
        except Exception as exc:
            messages.error(request, f'Charge failed: {exc}')

        return redirect(f"{account.get_absolute_url()}?tab=billing")


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookIngressView(View):
    """
    Public webhook endpoint for Stripe event ingestion.
    """

    def post(self, request):
        signature = request.headers.get('Stripe-Signature', '')
        payload = request.body or b''

        try:
            # NetBox object-change logging requires a concrete user.
            if not getattr(request.user, 'is_authenticated', False):
                cfg = settings.PLUGINS_CONFIG.get('netbox_billing', {})
                actor_username = cfg.get('webhook_actor_username', 'admin')
                actor = User.objects.filter(username=actor_username).first()
                if actor is None:
                    actor = User.objects.filter(is_superuser=True).order_by('id').first() or User.objects.order_by('id').first()
                if actor is None:
                    raise RuntimeError('No local user available for webhook change logging.')
                request.user = actor

            event, created, detail = services.parse_and_process_stripe_webhook(payload, signature)
            return JsonResponse(
                {
                    'ok': True,
                    'event_id': event.event_id,
                    'created': created,
                    'processed': event.processed,
                    'detail': detail,
                },
                status=200,
            )
        except Exception as exc:
            return JsonResponse(
                {
                    'ok': False,
                    'error': str(exc),
                },
                status=400,
            )


class StripeWebhookMetricsView(PermissionRequiredMixin, View):
    permission_required = 'netbox_billing.view_stripewebhookevent'

    def get(self, request):
        return JsonResponse(
            {
                'ok': True,
                'metrics': services.stripe_webhook_metrics(),
            },
            status=200,
        )
