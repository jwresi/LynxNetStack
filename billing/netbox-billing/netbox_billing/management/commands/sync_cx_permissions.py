from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from core.models import ObjectType
from users.models import Group, ObjectPermission


class Command(BaseCommand):
    help = 'Assign full customer-facing billing permissions to configured CX groups.'

    def handle(self, *args, **options):
        plugin_cfg = settings.PLUGINS_CONFIG.get('netbox_billing', {})
        cx_groups = plugin_cfg.get('cx_groups', ['cx', 'customer_experience', 'csr'])

        content_types = ContentType.objects.filter(app_label='netbox_billing')
        tenant_content_type = ContentType.objects.filter(app_label='tenancy', model='tenant')
        content_types = content_types | tenant_content_type
        billing_object_types = ObjectType.objects.filter(app_label='netbox_billing')
        tenant_object_types = ObjectType.objects.filter(app_label='tenancy', model='tenant')
        object_types = billing_object_types | tenant_object_types
        perms = list(
            Permission.objects.filter(content_type__in=content_types).filter(
                codename__regex=r'^(view|add|change|delete)_'
            )
        )

        for group_name in cx_groups:
            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.add(*perms)
            obj_perm, _ = ObjectPermission.objects.get_or_create(
                name=f'{group_name}-billing-cx',
                defaults={
                    'enabled': True,
                    'actions': ['view', 'add', 'change', 'delete'],
                    'constraints': {},
                },
            )
            obj_perm.enabled = True
            obj_perm.actions = ['view', 'add', 'change', 'delete']
            if obj_perm.constraints is None:
                obj_perm.constraints = {}
            obj_perm.save()
            obj_perm.groups.add(group)
            obj_perm.object_types.add(*object_types)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Granted {len(perms)} model perms + ObjectPermission to group "{group_name}"'
                )
            )
