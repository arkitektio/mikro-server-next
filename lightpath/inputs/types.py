import strawberry
from strawberry.experimental import pydantic
from typing import Optional, List


from lightpath.enums import ChannelKind, ObjectiveImmersion, PortRole, ElementKind, PulseKind
from lightpath.inputs import models  # your Pydantic input models


# ---- Small value types ----
@pydantic.input(models.Vec3InputModel, description="A 3D vector representing a point or offset in space.")
class Vec3Input:
    x: Optional[float] = strawberry.field(default=None, description="X coordinate of the vector.")
    y: Optional[float] = strawberry.field(default=None, description="Y coordinate of the vector.")
    z: Optional[float] = strawberry.field(default=None, description="Z coordinate of the vector.")


@pydantic.input(models.EulerInputModel, description="Euler angles representing rotation in 3D space.")
class EulerInput:
    rx: Optional[float] = strawberry.field(default=None, description="Rotation around the X axis, in degrees.")
    ry: Optional[float] = strawberry.field(default=None, description="Rotation around the Y axis, in degrees.")
    rz: Optional[float] = strawberry.field(default=None, description="Rotation around the Z axis, in degrees.")


@pydantic.input(models.Pose3DInputModel, description="A 3D pose consisting of position and orientation.")
class Pose3DInput:
    position: Optional[Vec3Input] = strawberry.field(default=None, description="3D position vector of the element.")
    orientation: Optional[EulerInput] = strawberry.field(default=None, description="3D orientation as Euler angles.")


@pydantic.input(models.SpectrumInputModel, description="Spectral window in nanometers for wavelength-dependent components.")
class SpectrumInput:
    min_nm: float = strawberry.field(description="Minimum wavelength supported, in nanometers.")
    max_nm: float = strawberry.field(description="Maximum wavelength supported, in nanometers.")


@pydantic.input(models.BeamStateInputModel, description="State of the optical beam on a particular path segment.")
class BeamStateInput:
    wavelength_nm: Optional[float] = strawberry.field(default=None, description="Nominal wavelength of the beam, in nm.")
    power_mw: Optional[float] = strawberry.field(default=None, description="Optical power of the beam, in milliwatts.")
    polarization: Optional[str] = strawberry.field(default=None, description="Polarization state (e.g., linear, circular).")
    mode_hint: Optional[str] = strawberry.field(default=None, description="Optional mode hint (e.g., TEM00).")


# ---- Port input ----
@pydantic.input(models.LightPortInputModel, description="Input definition for an optical port on an element.")
class LightPortInput:
    id:  strawberry.ID  = strawberry.field(default=None, description="Optional UUID of the port (provide for updates).")
    name: str = strawberry.field(description="Human-readable name for the port.")
    role: PortRole = strawberry.field(description="Directionality of the port: INPUT, OUTPUT, or BIDIRECTIONAL.")
    channel: ChannelKind = strawberry.field(default=ChannelKind.FREE_SPACE, description="Propagation channel type for the port.")
    spectrum: Optional[SpectrumInput] = strawberry.field(default=None, description="Spectral range supported by this port.")
    

# ---- Optical element input ----
@pydantic.input(models.OpticalElementInputModel, description="Input for creating or updating any optical element. Fill only fields relevant to the chosen `kind`.")
class OpticalElementInput:
    id:  strawberry.ID  = strawberry.field(default=None, description="Optional UUID of the element (provide for updates).")
    label: str = strawberry.field(description="Human-readable label for the optical element.")
    kind: ElementKind = strawberry.field(description="Kind of optical element (e.g., SOURCE, MIRROR, LENS).")
    pose: Optional[Pose3DInput] = strawberry.field(default=None, description="Optional spatial pose of the element.")
    ports: List[LightPortInput] = strawberry.field(description="List of optical ports belonging to the element.")
    manufacturer: Optional[str] = strawberry.field(default=None, description="Manufacturer of the optical element.")
    model: Optional[str] = strawberry.field(default=None, description="Model name or number of the optical element.")
    serial_number: Optional[str] = strawberry.field(default=None, description="Serial number of the optical element.")

    # Source-specific
    nominal_wavelength_nm: Optional[float] = strawberry.field(default=None, description="Nominal output wavelength for source elements, in nm.")
    power_mw: Optional[float] = strawberry.field(default=None, description="Output power for source elements, in milliwatts.")
    channel: Optional[ChannelKind] = strawberry.field(default=None, description="Channel type for source elements (overrides default if specified).")

    # Detector-specific
    nepd_w_per_sqrt_hz: Optional[float] = strawberry.field(default=None, description="Noise-equivalent power density for detector elements (W/√Hz).")

    # Mirror-specific
    angle_deg: Optional[float] = strawberry.field(default=None, description="Angle of incidence for mirrors, in degrees.")
    band_min_nm: Optional[float] = strawberry.field(default=None, description="Minimum wavelength of mirror coating band, in nm.")
    band_max_nm: Optional[float] = strawberry.field(default=None, description="Maximum wavelength of mirror coating band, in nm.")

    # Beam splitter-specific
    r_fraction: Optional[float] = strawberry.field(default=None, description="Reflectance fraction for beam splitters (0–1).")
    t_fraction: Optional[float] = strawberry.field(default=None, description="Transmittance fraction for beam splitters (0–1).")

    # Lens-specific
    focal_length_mm: Optional[float] = strawberry.field(default=None, description="Focal length for lens elements, in millimeters.")

    # Objective-specific
    magnification: Optional[float] = strawberry.field(default=None, description="Magnification factor for objectives (e.g., 20 for 20×).")
    numerical_aperture: Optional[float] = strawberry.field(default=None, description="Numerical aperture for objectives.")
    brand: Optional[str] = strawberry.field(default=None, description="Brand or manufacturer of the objective.")
    model: Optional[str] = strawberry.field(default=None, description="Model name or number of the objective.")
    working_distance_mm: Optional[float] = strawberry.field(default=None, description="Working distance for objectives, in millimeters.")
    immersion_medium: ObjectiveImmersion | None = strawberry.field(default=None, description="Immersion medium (e.g., 'OIL', 'WATER')")
    iris: bool | None = strawberry.field(default=False, description="Has iris (aperture stop)")
    amplifier_gain_db: float | None = strawberry.field(default=None, description="Amplifier gain (dB)")
    gain: float | None = strawberry.field(default=None, description="Overall gain (unitless)")

    # CCD-specific
    pixel_size_um: Optional[float] = strawberry.field(default=None, description="Pixel size (µm)")
    resolution: Optional[List[int]] =  strawberry.field(default=None, description="Pixel size (µm)")

    
    # Laser specific
    power_mw: float | None = strawberry.field(default=None, description="Source power (mW)")
    channel: ChannelKind | None  = strawberry.field(default=None, description="Output channel type")
    laser_medium: Optional[str] = strawberry.field(default=None, description="Laser medium (e.g., 'Ti:Sapphire', 'Nd:YAG')")
    pulse_kind: Optional[PulseKind] = strawberry.field(default=None, description="Pulse type (e.g., 'CW', 'PULSED')")
    repetition_rate_hz: Optional[float] = strawberry.field(default=None, description="Repetition rate (Hz)")
    has_pockels_cell: Optional[bool] = strawberry.field(default=None, description="Has Pockels cell")
    has_q_switch: Optional[bool] = strawberry.field(default=None, description="Has Q-switch")

# ---- Edge input ----
@pydantic.input(models.LightEdgeInputModel, description="Input for connecting two optical ports.")
class LightEdgeInput:
    id:str = strawberry.field(default=None, description="Optional UUID of the edge (provide for updates).")
    source_element_id: strawberry.ID = strawberry.field(description="UUID of the source element.")
    source_port_id:  strawberry.ID  = strawberry.field(description="UUID of the source port.")
    target_element_id:  strawberry.ID  = strawberry.field(description="UUID of the target element.")
    target_port_id:  strawberry.ID  = strawberry.field(description="UUID of the target port.")
    path_length_mm: Optional[float] = strawberry.field(default=None, description="Geometric path length between ports, in millimeters.")
    medium: Optional[str] = strawberry.field(default="AIR", description="Propagation medium for the edge (default is AIR).")
    loss_db: Optional[float] = strawberry.field(default=0.0, description="Insertion loss along this edge, in decibels.")
    beam: Optional[BeamStateInput] = strawberry.field(default=None, description="Beam state annotation for this edge.")


# ---- Graph input ----
@pydantic.input(models.LightpathGraphInputModel, description="Bulk input for a full lightpath graph, including elements and edges.")
class LightpathGraphInput:
    elements: List[OpticalElementInput] = strawberry.field(description="List of all optical elements to include in the graph.")
    edges: List[LightEdgeInput] = strawberry.field(description="List of all edges connecting elements in the graph.")
