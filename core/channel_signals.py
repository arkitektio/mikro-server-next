from pydantic import BaseModel


class ImageSignal(BaseModel):
    """A model representing an image event."""
    create: int | None = None
    update: int | None = None
    delete: int | None = None
    
    
class RoiSignal(BaseModel):
    """A model representing a region of interest event."""
    create: int | None = None
    update: int | None = None
    delete: int | None = None
    
    
class FileSignal(BaseModel):
    """A model representing a file event."""
    create: int | None = None
    update: int | None = None
    delete: int | None = None


class AffineTransformationViewSignal(BaseModel):
    """A model representing an affine transformation view event."""

    create: int | None = None
    update: int | None = None
    delete: int | None = None