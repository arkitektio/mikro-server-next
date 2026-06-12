import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from core import models
from core import channels
from guardian.shortcuts import assign_perm

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=models.RGBRenderContext)
def my_delete_handler(sender, instance=None, **kwargs):
    pass


@receiver(post_save, sender=models.Snapshot)
def my_snapshot_handler(sender, instance=None, created=None, **kwargs):
    if created:
        image = instance.image
        channels.image_channel.broadcast(
            channels.ImageSignal(update=image.id),
            [
                channels.org_images_room(image.organization_id),
                channels.dataset_images_room(image.dataset_id),
            ],
        )


def _roi_rooms(instance: models.ROI) -> list[str]:
    return [
        channels.org_rois_room(instance.image.organization_id),
        channels.image_rois_room(instance.image_id),
    ]


@receiver(post_save, sender=models.ROI)
def my_roi_handler(sender, instance=None, created=None, **kwargs):
    if created:
        channels.roi_channel.broadcast(channels.RoiSignal(create=instance.id), _roi_rooms(instance))
    else:
        channels.roi_channel.broadcast(channels.RoiSignal(update=instance.id), _roi_rooms(instance))


@receiver(pre_delete, sender=models.ROI)
def my_roi_delete_handler(sender, instance=None, **kwargs):
    channels.roi_channel.broadcast(channels.RoiSignal(delete=instance.id), _roi_rooms(instance))


def _image_rooms(instance: models.Image) -> list[str]:
    return [
        channels.org_images_room(instance.organization_id),
        channels.dataset_images_room(instance.dataset_id),
    ]


@receiver(post_save, sender=models.Image)
def my_image_handler(sender, instance=None, created=None, **kwargs):
    if created:
        assign_perm("inspect_image", instance.creator, instance)

        channels.image_channel.broadcast(channels.ImageSignal(create=instance.id), _image_rooms(instance))
    else:
        channels.image_channel.broadcast(channels.ImageSignal(update=instance.id), _image_rooms(instance))


@receiver(pre_delete, sender=models.Image)
def my_image_delete_handler(sender, instance=None, **kwargs):
    channels.image_channel.broadcast(channels.ImageSignal(delete=instance.id), _image_rooms(instance))


def _file_rooms(instance: models.File) -> list[str]:
    return [
        channels.org_files_room(instance.organization_id),
        channels.dataset_files_room(instance.dataset_id),
    ]


@receiver(post_save, sender=models.File)
def my_file_handler(sender, instance=None, created=None, **kwargs):
    if created:
        channels.file_channel.broadcast(channels.FileSignal(create=instance.id), _file_rooms(instance))
    else:
        channels.file_channel.broadcast(channels.FileSignal(update=instance.id), _file_rooms(instance))


@receiver(pre_delete, sender=models.File)
def my_file_delete_handler(sender, instance=None, **kwargs):
    channels.file_channel.broadcast(channels.FileSignal(delete=instance.id), _file_rooms(instance))


@receiver(post_save, sender=models.AffineTransformationView)
def my_affine_transformation_view_handler(sender, instance: models.AffineTransformationView | None = None, created=None, **kwargs):
    logger.debug("Broadcasting affine transformation view %s to stage %s", instance.id, instance.stage_id)
    if created:
        channels.affine_transformation_view_channel.broadcast(
            channels.AffineTransformationViewSignal(create=instance.id),
            [channels.stage_views_room(instance.stage_id)],
        )
    else:
        channels.affine_transformation_view_channel.broadcast(
            channels.AffineTransformationViewSignal(update=instance.id),
            [channels.stage_views_room(instance.stage_id)],
        )


@receiver(pre_delete, sender=models.AffineTransformationView)
def my_affine_transformation_view__delete_handler(sender, instance=None, **kwargs):
    channels.affine_transformation_view_channel.broadcast(
        channels.AffineTransformationViewSignal(delete=instance.id),
        [channels.stage_views_room(instance.stage_id)],
    )
