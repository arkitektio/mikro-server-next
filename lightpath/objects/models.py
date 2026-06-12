from __future__ import annotations
from typing import Annotated, Optional, List, Union, Literal, Tuple
from pydantic import BaseModel, Field, ConfigDict,  Discriminator
from uuid import uuid4
from lightpath.enums import PulseKind, ChannelKind, PortRole, ElementKind, FilterKind, ObjectiveImmersion, ObjectiveCorrectionKind


# ---- Geometry / beam annotations ----
class Vec3Model(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None


class EulerModel(BaseModel):
    rx: Optional[float] = None
    ry: Optional[float] = None
    rz: Optional[float] = None


class Pose3DModel(BaseModel):
    position: Optional[Vec3Model] = None
    orientation: Optional[EulerModel] = None


class SpectrumModel(BaseModel):
    min_nm: float
    max_nm: float


class BeamStateModel(BaseModel):
    wavelength_nm: Optional[float] = None
    power_mw: Optional[float] = None
    polarization: Optional[str] = None
    mode_hint: Optional[str] = None  # e.g. TEM00


# ---- Ports ----
class LightPortModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4))
    name: str
    role: PortRole
    channel: ChannelKind = ChannelKind.FREE_SPACE
    spectrum: Optional[SpectrumModel] = None
    max_incoming_edges: Optional[int] = None  # allow merges

    @property
    def is_input(self) -> bool:
        return self.role  == PortRole.INPUT

    @property
    def is_output(self) -> bool:
        return self.role == PortRole.OUTPUT


# ---- Optical element base + subtypes (inline fields, no nested params) ----
class OpticalElementBaseModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: str(uuid4))
    label: str
    kind: ElementKind
    pose: Optional[Pose3DModel] = None
    ports: List[LightPortModel] = Field(default_factory=list)
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    
class LampElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.LAMP] = ElementKind.LAMP
    channel: ChannelKind | None = ChannelKind.FREE_SPACE
    lamp_type: Optional[str] = None  # e.g., LED, Halogen, Xenon, Mercury, etc.


class OtherSourceElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.OTHER_SOURCE] = ElementKind.OTHER_SOURCE
    channel: ChannelKind | None = ChannelKind.FREE_SPACE
    lamp_type: Optional[str] = None  # e.g., LED, Halogen, Xenon, Mercury, etc.

class LaserElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.LASER] = ElementKind.LASER
    nominal_wavelength_nm: float
    power_mw: Optional[float] = None
    channel: ChannelKind | None = ChannelKind.FREE_SPACE
    laser_medium: Optional[str] = None
    pulse_kind: Optional[PulseKind] = None
    repetition_rate_hz: Optional[float] = None
    has_pockels_cell: Optional[bool] = None
    has_q_switch: Optional[bool] = None

class DetectorElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.DETECTOR] = ElementKind.DETECTOR
    nepd_w_per_sqrt_hz: Optional[float] = None
    
    
class PinholeElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.PINHOLE] = ElementKind.PINHOLE
    diameter_um: Optional[float] = None


class MirrorElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.MIRROR] = ElementKind.MIRROR
    angle_deg: Optional[float] = None
    band: Optional[SpectrumModel] = None


class BeamSplitterElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.BEAM_SPLITTER] = ElementKind.BEAM_SPLITTER
    r_fraction: float = 0.5
    t_fraction: float = 0.5
    band: Optional[SpectrumModel] = None


class LensElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.LENS] = ElementKind.LENS
    focal_length_mm: float | None
    
    
class CCDElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.CCD] = ElementKind.CCD
    pixel_size_um: Optional[float] = None
    resolution: Optional[Tuple[int, int]] = None  # (width, height)
    
    
class SampleElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.SAMPLE] = ElementKind.SAMPLE
    description: Optional[str] = None


class FilterElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.FILTER] = ElementKind.FILTER
    description: Optional[str] = None
    filter_kind: Optional[FilterKind] = None
    transmittance: Optional[float] = None  # 0-1


class OtherElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.OTHER] = ElementKind.OTHER
    description: Optional[str] = None

class ObjectiveElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.OBJECTIVE] = ElementKind.OBJECTIVE
    magnification: float | None = None
    numerical_aperture: float | None = None
    working_distance_mm: Optional[float] = None
    immersion_medium: Optional[ObjectiveImmersion] = None
    correction_kind: Optional[ObjectiveCorrectionKind] = None

# (Extend with Objective/Filter/Polarizer/etc. using the same pattern)

OpticalElementUnion = Annotated[
    Union[
        OtherSourceElementModel,
        LaserElementModel,
        DetectorElementModel,
        LampElementModel,
        MirrorElementModel,
        PinholeElementModel,
        BeamSplitterElementModel,
        LensElementModel,
        SampleElementModel,
        OtherElementModel,
        ObjectiveElementModel,
        FilterElementModel,
        CCDElementModel,
    ],
    Discriminator("kind")
]


# ---- Graph edges + graph ----
class LightEdgeModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4))
    source_element_id: str = Field(default_factory=lambda: str(uuid4))
    source_port_id: str = Field(default_factory=lambda: str(uuid4))
    target_element_id: str = Field(default_factory=lambda: str(uuid4))
    target_port_id: str = Field(default_factory=lambda: str(uuid4))
    path_length_mm: Optional[float] = None
    medium: Optional[str] = "AIR"
    loss_db: Optional[float] = 0.0
    beam: Optional[BeamStateModel] = None


class LightpathGraphModel(BaseModel):
    elements: List[OpticalElementUnion] = Field(default_factory=list)
    edges: List[LightEdgeModel] = Field(default_factory=list)

    