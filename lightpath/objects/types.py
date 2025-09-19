import datetime
from typing import Optional, List, Dict, Union, Literal, Tuple

import strawberry
import strawberry_django
from pydantic import BaseModel, Field
from strawberry import LazyType
from strawberry.experimental import pydantic

from lightpath.objects import models
from lightpath.enums import ChannelKind, PortRole, ElementKind
from uuid import uuid4

# ---- Geometry / beam annotations ----
@pydantic.type(models.Vec3Model, description="3D vector or point in space")
class Vec3:
    x: Optional[float] = strawberry.field(default=None, description="X coordinate")
    y: Optional[float] = strawberry.field(default=None, description="Y coordinate")
    z: Optional[float] = strawberry.field(default=None, description="Z coordinate")


@pydantic.type(models.EulerModel,description="Euler angles for 3D orientation")
class Euler:
    rx: Optional[float] = strawberry.field(default=None, description="Rotation around X axis in degrees")
    ry: Optional[float] = strawberry.field(default=None, description="Rotation around Y axis in degrees")
    rz: Optional[float] = strawberry.field(default=None, description="Rotation around Z axis in degrees")


@pydantic.type(models.Pose3DModel, description="Optional 3D pose; position and/or orientation can be omitted")
class Pose3D:
    position: Optional[Vec3] = strawberry.field(default=None, description="XYZ position (optional)")
    orientation: Optional[Euler] = strawberry.field(default=None, description="Euler orientation (optional)")


@pydantic.type(models.SpectrumModel, description="Spectral window in nanometers")
class Spectrum:
    min_nm: float = strawberry.field(description="Minimum wavelength (nm)")
    max_nm: float = strawberry.field(description="Maximum wavelength (nm)")


@pydantic.type(models.BeamStateModel, description="Beam properties carried on a light edge")
class BeamState:
    wavelength_nm: float | None = strawberry.field(default=None, description="Wavelength (nm)")
    power_mw: float | None = strawberry.field(default=None, description="Optical power (mW)")
    polarization: str | None = strawberry.field(default=None, description="Polarization label")
    mode_hint: str | None = strawberry.field(default=None, description="Mode hint, e.g., TEM00")


# ---------- Port ----------
@pydantic.type(models.LightPortModel, description="Optical port on an element")
class LightPort:
    id: strawberry.ID = strawberry.field(description="Port UUID")
    name: str = strawberry.field(description="Port name")
    role: PortRole = strawberry.field(description="Port role")
    channel: ChannelKind = strawberry.field(description="Channel type")
    spectrum: Spectrum | None = strawberry.field(default=None, description="Supported spectrum")
    max_incoming_edges: int | None = strawberry.field(default=None, description="Max fan-in (for merges)")


# ---------- Optical Element Interface ----------
@strawberry.interface(description="Common interface for all optical elements")
class OpticalElement:
    id: strawberry.ID
    label: str
    kind: ElementKind
    pose: Pose3D | None
    ports: list[LightPort]


# ---------- Element Subtypes (inline fields, no nested params) ----------
@pydantic.type(models.SourceElementModel, description="Light source")
class SourceElement(OpticalElement):
    id: strawberry.ID
    label: str
    kind: ElementKind
    pose: Pose3D | None
    ports: list[LightPort]

    nominal_wavelength_nm: float | None = strawberry.field(default=None, description="Source wavelength (nm)")
    power_mw: float | None = strawberry.field(default=None, description="Source power (mW)")
    channel: ChannelKind | None  = strawberry.field(default=None, description="Output channel type")


@pydantic.type(models.DetectorElementModel, description="Detector")
class DetectorElement(OpticalElement):
    id: strawberry.ID
    label: str
    kind: ElementKind
    pose: Pose3D | None
    ports: list[LightPort]

    nepd_w_per_sqrt_hz: float | None = strawberry.field(default=None, description="Noise-equivalent power density")


@pydantic.type(models.MirrorElementModel, description="Mirror")
class MirrorElement(OpticalElement):
    id: strawberry.ID
    label: str
    kind: ElementKind
    pose: Pose3D | None
    ports: list[LightPort]

    angle_deg: float | None = strawberry.field(default=None, description="Nominal incidence angle (deg)")
    band: Spectrum | None = strawberry.field(default=None, description="Coating band")


@pydantic.type(models.BeamSplitterElementModel, description="Beam splitter")
class BeamSplitterElement(OpticalElement):
    id: strawberry.ID
    label: str
    kind: ElementKind
    pose: Pose3D | None
    ports: list[LightPort]

    r_fraction: float = strawberry.field(description="Reflectance fraction (0–1)")
    t_fraction: float = strawberry.field(description="Transmittance fraction (0–1)")
    band: Spectrum | None = strawberry.field(default=None, description="Coating band")


@pydantic.type(models.LensElementModel, description="Thin lens")
class LensElement(OpticalElement):
    id: strawberry.ID
    label: str
    kind: ElementKind
    pose: Pose3D | None
    ports: list[LightPort]

    focal_length_mm: float = strawberry.field(description="Focal length (mm)")

@pydantic.type(models.SampleElementModel, description="The sample")
class SampleElement(OpticalElement):
    id: strawberry.ID
    label: str
    kind: ElementKind

@pydantic.type(models.ObjectiveElementModel, description="Microscope objective")
class ObjectiveElement(OpticalElement):
    id: strawberry.ID
    label: str
    kind: ElementKind
    pose: Pose3D | None
    ports: list[LightPort]

    magnification: float | None = strawberry.field(default=None,description="Magnification (e.g., 20 for 20x)")
    numerical_aperture: float | None = strawberry.field(default=None,description="NA")
    brand: str | None = strawberry.field(default=None)
    model: str | None = strawberry.field(default=None)
    working_distance_mm: float | None = strawberry.field(default=None, description="Working distance (mm)")


# ---------- Edge ----------
@pydantic.type(models.LightEdgeModel, description="Directed edge connecting two ports")
class LightEdge:
    id: strawberry.ID = strawberry.field(description="Edge UUID")
    source_element_id: strawberry.ID = strawberry.field(description="Source element UUID")
    source_port_id: strawberry.ID = strawberry.field(description="Source port UUID")
    target_element_id: strawberry.ID = strawberry.field(description="Target element UUID")
    target_port_id: strawberry.ID = strawberry.field(description="Target port UUID")
    path_length_mm: float | None = strawberry.field(default=None, description="Path length (mm)")
    medium: str | None = strawberry.field(default="AIR", description="Propagation medium")
    loss_db: float | None = strawberry.field(default=0.0, description="Insertion loss (dB)")
    beam: BeamState | None = strawberry.field(default=None, description="Beam state annotation")


# ---------- Graph DTO ----------
@pydantic.type(models.LightpathGraphModel, description="Graph of optical elements and edges")
class LightpathGraph:
    elements: list[OpticalElement] = strawberry.field(description="All elements in the graph")
    edges: list[LightEdge] = strawberry.field(description="All edges in the graph")


