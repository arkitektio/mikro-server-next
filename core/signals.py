from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from core import models
from core.channel import image_broadcast
from core import managers
from core import models

@receiver(pre_delete, sender=models.RGBRenderContext)
def my_delete_handler(sender, instance=None, **kwargs):
    print("NEEDS TO IMPLEMENT DELETETING VACANT VIEWS")



@receiver(post_save, sender=models.Image)
def my_handler(sender, instance=None, created=None, **kwargs):

    if created:
        # Lets outcreated some views
        print("Creating Views")
        managers.auto_create_views(instance)





    image_broadcast(instance.id)
