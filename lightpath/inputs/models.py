from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
from uuid import UUID

from kanne_server import quantities
from lightpath.enums import ChannelKind, PortRole, ElementKind, ObjectiveImmersion, PulseKind


class Vec3InputModel(BaseModel):
    """3D vector for input."""

    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None


class EulerInputModel(BaseModel):
    """Euler angles for input."""

    rx: Optional[float] = None
    ry: Optional[float] = None
    rz: Optional[float] = None


class Pose3DInputModel(BaseModel):
    """Pose with optional position and orientation."""

    position: Optional[Vec3InputModel] = None
    orientation: Optional[EulerInputModel] = None


class SpectrumInputModel(BaseModel):
    """Spectral window."""

    min: quantities.Length
    max: quantities.Length


class BeamStateInputModel(BaseModel):
    """Beam properties for input edges."""

    wavelength: Optional[quantities.Length] = None
    power: Optional[quantities.Power] = None
    polarization: Optional[str] = None
    mode_hint: Optional[str] = None


class LightPortInputModel(BaseModel):
    """Port definition for input."""

    id: Optional[UUID] = None  # optional: may be generated server-side
    name: str
    role: PortRole
    channel: ChannelKind = ChannelKind.FREE_SPACE
    spectrum: Optional[SpectrumInputModel] = None
    max_incoming_edges: Optional[int] = None


class OpticalElementInputModel(BaseModel):
    """
    Single input model for creating/updating any optical element.
    Only fill the fields relevant to the chosen `kind`.
    """

    id: Optional[str] = None
    label: str
    kind: ElementKind
    pose: Optional[Pose3DInputModel] = None
    ports: List[LightPortInputModel]
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None

    # Source-specific
    nominal_wavelength: Optional[quantities.Length] = None
    channel: Optional[ChannelKind] = None

    # Pinhole-specific
    diameter: Optional[quantities.Length] = None

    # Detector-specific
    nepd_w_per_sqrt_hz: Optional[float] = None
    # Mirror-specific
    angle_deg: Optional[float] = None
    band_min: Optional[quantities.Length] = None
    band_max: Optional[quantities.Length] = None
    # Beam splitter-specific
    r_fraction: Optional[float] = None
    t_fraction: Optional[float] = None

    # Lens-specific
    focal_length: Optional[quantities.Length] = None

    # Objective-specific
    magnification: Optional[float] = None
    numerical_aperture: Optional[float] = None
    brand: Optional[str] = None
    working_distance: Optional[quantities.Length] = None
    immersion_medium: ObjectiveImmersion | None = None
    iris: bool | None = None
    amplifier_gain_db: float | None = None
    gain: float | None = None

    # CCD-specific
    pixel_size: Optional[quantities.Length] = None
    resolution: Optional[List[int]] = None

    # Laser specific
    power: quantities.Power | None = None
    laser_medium: Optional[str] = None
    pulse_kind: Optional[PulseKind] = None
    repetition_rate: Optional[quantities.Frequency] = None
    has_pockels_cell: Optional[bool] = None
    has_q_switch: Optional[bool] = None


class LightEdgeInputModel(BaseModel):
    """Input model for connecting two ports."""

    id: Optional[UUID] = None
    source_element_id: UUID
    source_port_id: UUID
    target_element_id: UUID
    target_port_id: UUID
    path_length: Optional[quantities.Length] = None
    medium: Optional[str] = Field(default="AIR")
    loss_db: Optional[float] = Field(default=0.0)
    beam: Optional[BeamStateInputModel] = None


class LightpathGraphInputModel(BaseModel):
    """Bulk graph input model for elements and edges."""

    elements: List[OpticalElementInputModel]
    edges: List[LightEdgeInputModel]
