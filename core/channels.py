from kante.channel import build_channel
from .channel_signals import RoiSignal, ImageSignal, FileSignal, AffineTransformationViewSignal


roi_channel = build_channel(RoiSignal)
image_channel = build_channel(ImageSignal)
file_channel = build_channel(FileSignal)

affine_transformation_view_channel = build_channel(AffineTransformationViewSignal)
    

