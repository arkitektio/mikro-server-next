from __future__ import annotations
from typing import Annotated, Optional, List, Dict, Union, Literal, Tuple
from pydantic import BaseModel, Field, ConfigDict,  Discriminator, Tag
from enum import Enum
from uuid import UUID, uuid4
from lightpath.enums import ChannelKind, PortRole, ElementKind


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
        return self.role in (PortRole.INPUT, PortRole.BIDIRECTIONAL)

    @property
    def is_output(self) -> bool:
        return self.role in (PortRole.OUTPUT, PortRole.BIDIRECTIONAL)


# ---- Optical element base + subtypes (inline fields, no nested params) ----
class OpticalElementBaseModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: str(uuid4))
    label: str
    kind: ElementKind
    pose: Optional[Pose3DModel] = None
    ports: List[LightPortModel]


class SourceElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.SOURCE] = ElementKind.SOURCE
    nominal_wavelength_nm: Optional[float] = None
    power_mw: Optional[float] = None
    channel: ChannelKind | None = ChannelKind.FREE_SPACE


class DetectorElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.DETECTOR] = ElementKind.DETECTOR
    nepd_w_per_sqrt_hz: Optional[float] = None


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
    
    
class SampleElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.SAMPLE] = ElementKind.SAMPLE
    description: Optional[str] = None



class ObjectiveElementModel(OpticalElementBaseModel):
    kind: Literal[ElementKind.OBJECTIVE] = ElementKind.OBJECTIVE
    magnification: float | None = None
    numerical_aperture: float | None = None
    brand: Optional[str] = None
    model: Optional[str] = None
    working_distance_mm: Optional[float] = None

# (Extend with Objective/Filter/Polarizer/etc. using the same pattern)

OpticalElementUnion = Annotated[
    Union[
        SourceElementModel,
        DetectorElementModel,
        MirrorElementModel,
        BeamSplitterElementModel,
        LensElementModel,
        SampleElementModel,
        ObjectiveElementModel,
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

    