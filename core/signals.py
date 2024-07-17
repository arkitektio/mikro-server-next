from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from core import models
from core.channel import image_broadcast, roi_update_broadcast
from core import managers
from core import models

@receiver(pre_delete, sender=models.RGBRenderContext)
def my_delete_handler(sender, instance=None, **kwargs):
    print("NEEDS TO IMPLEMENT DELETETING VACANT VIEWS")



@receiver(post_save, sender=models.Image)
def my_handler(sender, instance=None, created=None, **kwargs):

    image_broadcast(instance.id, ["images"])


@receiver(post_save, sender=models.ROI)
def my_roi_handler(sender, instance=None, created=None, **kwargs):
    print("ROI HANDLER")
    roi_update_broadcast({"id": instance.id, "type": "create" if created else "update"}, ["rois", f"image_roi_{instance.image.id}"] )

@receiver(pre_delete, sender=models.ROI)
def my_roi_delete_handler(sender, instance=None, **kwargs):
    roi_update_broadcast({"id": instance.id, "type": "delete"}, ["rois", f"image_roi_{instance.image.id}"])
