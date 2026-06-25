from kante.channel import build_channel
from .channel_signals import RoiSignal, ImageSignal, FileSignal, AffineTransformationViewSignal


roi_channel = build_channel(RoiSignal)
image_channel = build_channel(ImageSignal)
file_channel = build_channel(FileSignal)

affine_transformation_view_channel = build_channel(AffineTransformationViewSignal)


# Room names are built in one place so the broadcasting signals and the
# subscribing resolvers cannot drift apart. The org-wide rooms carry the
# organization id so cross-tenant events never share a room.


def org_images_room(org_id: int) -> str:
    return f"org_{org_id}_images"


def dataset_images_room(dataset_id: int) -> str:
    return f"dataset_images_{dataset_id}"


def org_files_room(org_id: int) -> str:
    return f"org_{org_id}_files"


def dataset_files_room(dataset_id: int) -> str:
    return f"dataset_files_{dataset_id}"


def org_rois_room(org_id: int) -> str:
    return f"org_{org_id}_rois"


def image_rois_room(image_id: int) -> str:
    return f"image_roi_{image_id}"


def stage_views_room(stage_id: int) -> str:
    return f"stage_view_{stage_id}"
