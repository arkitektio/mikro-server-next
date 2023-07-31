from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import Image
from core.channel import image_broadcast


@receiver(post_save, sender=Image)
def my_handler(sender, **kwargs):
    image_broadcast(kwargs["instance"].id)
