from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def setup_roles(sender, **kwargs):
    pass
