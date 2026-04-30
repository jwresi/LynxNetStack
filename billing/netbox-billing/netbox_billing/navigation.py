from django.conf import settings
from django.utils.translation import gettext_lazy as _
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

plugin_settings = settings.PLUGINS_CONFIG.get('netbox_billing', {})


def add_button(link, permission):
    return PluginMenuButton(
        link=link,
        title=_('Add'),
        icon_class='mdi mdi-plus-thick',
        permissions=[permission],
    )


customer_items = (
    PluginMenuItem(
        link='plugins:netbox_billing:cx_dashboard',
        link_text=_('CX Console'),
        permissions=['netbox_billing.view_billingaccount'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:billingaccount_list',
        link_text=_('Customers'),
        buttons=[add_button('plugins:netbox_billing:billingaccount_add', 'netbox_billing.add_billingaccount')],
        permissions=['netbox_billing.view_billingaccount'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:customerprofile_list',
        link_text=_('Customer Profiles'),
        buttons=[add_button('plugins:netbox_billing:customerprofile_add', 'netbox_billing.add_customerprofile')],
        permissions=['netbox_billing.view_customerprofile'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:customerlabel_list',
        link_text=_('Customer Labels'),
        buttons=[add_button('plugins:netbox_billing:customerlabel_add', 'netbox_billing.add_customerlabel')],
        permissions=['netbox_billing.view_customerlabel'],
    ),
)

service_items = (
    PluginMenuItem(
        link='plugins:netbox_billing:tariffplan_list',
        link_text=_('Tariff Plans'),
        buttons=[add_button('plugins:netbox_billing:tariffplan_add', 'netbox_billing.add_tariffplan')],
        permissions=['netbox_billing.view_tariffplan'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:tariffbundle_list',
        link_text=_('Bundles'),
        buttons=[add_button('plugins:netbox_billing:tariffbundle_add', 'netbox_billing.add_tariffbundle')],
        permissions=['netbox_billing.view_tariffbundle'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:subscription_list',
        link_text=_('Services'),
        buttons=[add_button('plugins:netbox_billing:subscription_add', 'netbox_billing.add_subscription')],
        permissions=['netbox_billing.view_subscription'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:property_list',
        link_text=_('Properties'),
        buttons=[add_button('plugins:netbox_billing:property_add', 'netbox_billing.add_property')],
        permissions=['netbox_billing.view_property'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:unit_list',
        link_text=_('Units'),
        buttons=[add_button('plugins:netbox_billing:unit_add', 'netbox_billing.add_unit')],
        permissions=['netbox_billing.view_unit'],
    ),
)

finance_items = (
    PluginMenuItem(
        link='plugins:netbox_billing:invoice_list',
        link_text=_('Finance Documents'),
        buttons=[add_button('plugins:netbox_billing:invoice_add', 'netbox_billing.add_invoice')],
        permissions=['netbox_billing.view_invoice'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:payment_list',
        link_text=_('Transactions'),
        buttons=[add_button('plugins:netbox_billing:payment_add', 'netbox_billing.add_payment')],
        permissions=['netbox_billing.view_payment'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:scheduledpayment_list',
        link_text=_('Scheduled Payments'),
        buttons=[add_button('plugins:netbox_billing:scheduledpayment_add', 'netbox_billing.add_scheduledpayment')],
        permissions=['netbox_billing.view_scheduledpayment'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:customerdocument_list',
        link_text=_('Documents'),
        buttons=[add_button('plugins:netbox_billing:customerdocument_add', 'netbox_billing.add_customerdocument')],
        permissions=['netbox_billing.view_customerdocument'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:customercommunication_list',
        link_text=_('Communication'),
        buttons=[add_button('plugins:netbox_billing:customercommunication_add', 'netbox_billing.add_customercommunication')],
        permissions=['netbox_billing.view_customercommunication'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:customernote_list',
        link_text=_('Comments / To-dos'),
        buttons=[add_button('plugins:netbox_billing:customernote_add', 'netbox_billing.add_customernote')],
        permissions=['netbox_billing.view_customernote'],
    ),
    PluginMenuItem(
        link='plugins:netbox_billing:stripewebhookevent_list',
        link_text=_('Stripe Webhook Events'),
        buttons=[add_button('plugins:netbox_billing:stripewebhookevent_add', 'netbox_billing.add_stripewebhookevent')],
        permissions=['netbox_billing.view_stripewebhookevent'],
    ),
)

if plugin_settings.get('top_level_menu', True):
    menu = PluginMenu(
        label=_('Billing'),
        groups=(
            (_('Customers'), customer_items),
            (_('Services'), service_items),
            (_('Finance'), finance_items),
        ),
        icon_class='mdi mdi-credit-card-outline',
    )
else:
    menu_items = customer_items + service_items + finance_items
