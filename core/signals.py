from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from core import models
from core import channels
from core import managers
from core import models


@receiver(pre_delete, sender=models.RGBRenderContext)
def my_delete_handler(sender, instance=None, **kwargs):
    pass


@receiver(post_save, sender=models.Snapshot)
def my_snapshot_handler(sender, instance=None, created=None, **kwargs):
    if created:
        channels.image_channel.broadcast(
            channels.ImageSignal(update=instance.image.id),
            ["images"] + [f"dataset_images_{instance.image.dataset.id}"],
        )


@receiver(post_save, sender=models.ROI)
def my_roi_handler(sender, instance=None, created=None, **kwargs):
    if created:
        channels.roi_channel.broadcast(
            channels.RoiSignal(create=instance.id),
            ["rois", f"image_roi_{instance.image.id}"],
        )
    else:
        channels.roi_channel.broadcast(
            channels.RoiSignal(update=instance.id),
            ["rois", f"image_roi_{instance.image.id}"],
        )
      

@receiver(pre_delete, sender=models.ROI)
def my_roi_delete_handler(sender, instance=None, **kwargs):
     channels.roi_channel.broadcast(
        channels.RoiSignal(delete=instance.id),
        ["rois", f"image_roi_{instance.image.id}"],
    )


@receiver(post_save, sender=models.Image)
def my_image_handler(sender, instance=None, created=None, **kwargs):
    if created:
        channels.image_channel.broadcast(
            channels.ImageSignal(create=instance.id),
            ["images", f"image_roi_{instance.dataset.id}"],
        )
    else:
        channels.image_channel.broadcast(
            channels.ImageSignal(update=instance.id),
            ["images", f"image_roi_{instance.dataset.id}"],
        )
      

@receiver(pre_delete, sender=models.Image)
def my_image_delete_handler(sender, instance=None, **kwargs):
     channels.image_channel.broadcast(
        channels.ImageSignal(delete=instance.id),
        ["rois", f"image_roi_{instance.dataset.id}"],
    )


@receiver(post_save, sender=models.File)
def my_file_handler(sender, instance=None, created=None, **kwargs):
    if created:
        channels.file_channel.broadcast(
            channels.FileSignal(create=instance.id),
            ["files", f"file_dataset_{instance.dataset.id}"],
        )
    else:
        channels.file_channel.broadcast(
            channels.FileSignal(update=instance.id),
            ["files", f"file_dataset_{instance.dataset.id}"],
        )
      

@receiver(pre_delete, sender=models.File)
def my_file_delete_handler(sender, instance=None, **kwargs):
     channels.image_channel.broadcast(
        channels.FileSignal(delete=instance.id),
        ["files", f"file_dataset_{instance.dataset.id}"],
    )
