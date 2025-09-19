from enum import Enum
import strawberry


# ---- Enums (shared by models & GraphQL) ----
@strawberry.enum
class ChannelKind(str, Enum):
    FREE_SPACE = "FREE_SPACE"
    FIBER_SM = "FIBER_SM"
    FIBER_MM = "FIBER_MM"
    WAVEGUIDE = "WAVEGUIDE"

@strawberry.enum
class PortRole(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


@strawberry.enum
class ElementKind(str, Enum):
    SOURCE = "SOURCE"
    DETECTOR = "DETECTOR"
    MIRROR = "MIRROR"
    BEAM_SPLITTER = "BEAM_SPLITTER"
    LENS = "LENS"
    OBJECTIVE = "OBJECTIVE"
    FILTER = "FILTER"
    POLARIZER = "POLARIZER"
    WAVEPLATE = "WAVEPLATE"
    APERTURE = "APERTURE"
    SHUTTER = "SHUTTER"
    SAMPLE = "SAMPLE"
    OTHER = "OTHER"