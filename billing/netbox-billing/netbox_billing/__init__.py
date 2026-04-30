from netbox.plugins import PluginConfig


class NetBoxBillingConfig(PluginConfig):
    name = 'netbox_billing'
    verbose_name = 'NetBox Billing'
    description = 'Unified billing, tariffs, properties, subscriptions, and invoicing'
    version = '0.1.0'
    author = 'Local'
    author_email = 'noreply@example.com'
    base_url = 'billing'
    min_version = '4.1.11'
    max_version = '4.1.11'
    required_settings = []
    default_settings = {
        'top_level_menu': True,
        'cx_groups': ['cx', 'customer_experience', 'csr'],
        'stripe_api_key': '',
        'stripe_webhook_secret': '',
        'webhook_actor_username': 'admin',
    }


config = NetBoxBillingConfig
