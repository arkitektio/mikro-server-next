"""
ROI calculation utilities for determining bounding boxes and spatial extents.
"""
from dataclasses import dataclass
from typing import List, Any, Optional, TYPE_CHECKING
import numpy as np
from core import enums

if TYPE_CHECKING:
    from core.models import ROI


@dataclass
class ROIBounds:
    """
    Represents the bounding box coordinates for an ROI.
    
    All coordinates are optional and will be None if not applicable
    for the specific ROI type.
    """
    min_x: Optional[int] = None
    max_x: Optional[int] = None
    min_y: Optional[int] = None
    max_y: Optional[int] = None
    min_z: Optional[int] = None
    max_z: Optional[int] = None
    min_t: Optional[int] = None
    max_t: Optional[int] = None
    min_c: Optional[int] = None
    max_c: Optional[int] = None
    
    @property
    def width(self) -> Optional[int]:
        """Calculate width (x dimension) if bounds are available."""
        if self.min_x is not None and self.max_x is not None:
            return self.max_x - self.min_x
        return None
    
    @property
    def height(self) -> Optional[int]:
        """Calculate height (y dimension) if bounds are available."""
        if self.min_y is not None and self.max_y is not None:
            return self.max_y - self.min_y
        return None
    
    @property
    def depth(self) -> Optional[int]:
        """Calculate depth (z dimension) if bounds are available."""
        if self.min_z is not None and self.max_z is not None:
            return self.max_z - self.min_z
        return None
    
    @property
    def duration(self) -> Optional[int]:
        """Calculate duration (t dimension) if bounds are available."""
        if self.min_t is not None and self.max_t is not None:
            return self.max_t - self.min_t
        return None
    
    @property
    def channels(self) -> Optional[int]:
        """Calculate number of channels (c dimension) if bounds are available."""
        if self.min_c is not None and self.max_c is not None:
            return self.max_c - self.min_c + 1  # +1 because channels are inclusive
        return None
    
    @property
    def area(self) -> Optional[int]:
        """Calculate 2D area if x and y bounds are available."""
        width, height = self.width, self.height
        if width is not None and height is not None:
            return width * height
        return None
    
    @property
    def volume(self) -> Optional[int]:
        """Calculate 3D volume if x, y, and z bounds are available."""
        area, depth = self.area, self.depth
        if area is not None and depth is not None:
            return area * depth
        return None
    
    def has_bounds(self) -> bool:
        """Check if any bounds are set."""
        return any([
            self.min_x is not None, self.max_x is not None,
            self.min_y is not None, self.max_y is not None,
            self.min_z is not None, self.max_z is not None,
            self.min_t is not None, self.max_t is not None,
            self.min_c is not None, self.max_c is not None,
        ])
    
    def to_dict(self) -> dict[str, Optional[int]]:
        """Convert to dictionary format for backward compatibility."""
        return {
            'min_x': self.min_x, 'max_x': self.max_x,
            'min_y': self.min_y, 'max_y': self.max_y,
            'min_z': self.min_z, 'max_z': self.max_z,
            'min_t': self.min_t, 'max_t': self.max_t,
            'min_c': self.min_c, 'max_c': self.max_c,
        }


def _extract_coordinates(vectors: List[Any]) -> np.ndarray:
    """
    Extract 5D coordinates from vector data.
    
    Args:
        vectors: List of vectors, each is a list with dimensions [c, t, z, y, x]
        
    Returns:
        numpy array of shape (n_points, 5) with coordinates [x, y, z, t, c]
    """
    if not vectors:
        return np.empty((0, 5))
    
    coords = []
    for vector in vectors:
        if isinstance(vector, (list, tuple)) and len(vector) >= 5:
            # Input format: [c, t, z, y, x]
            # Output format: [x, y, z, t, c]
            c, t, z, y, x = vector[:5]
            coords.append([x, y, z, t, c])
        else:
            # Fallback for incomplete vectors
            coords.append([0, 0, 0, 0, 0])
    
    return np.array(coords)


def _bounds_from_coordinates(coords: np.ndarray) -> ROIBounds:
    """
    Calculate bounds from coordinate array.
    
    Args:
        coords: numpy array of shape (n_points, 5) with coordinates [x, y, z, t, c]
        
    Returns:
        ROIBounds object with calculated min/max values
    """
    if coords.size == 0:
        return ROIBounds()
    
    mins = np.min(coords, axis=0)
    maxs = np.max(coords, axis=0)
    
    return ROIBounds(
        min_x=int(mins[0]), max_x=int(maxs[0]),
        min_y=int(mins[1]), max_y=int(maxs[1]),
        min_z=int(mins[2]), max_z=int(maxs[2]),
        min_t=int(mins[3]), max_t=int(maxs[3]),
        min_c=int(mins[4]), max_c=int(maxs[4])
    )


def calculate_roi_bounds(
    vectors: List[Any], 
    kind: str
) -> ROIBounds:
    """
    Calculate the minimum and maximum coordinates for an ROI based on its vectors and kind.
    
    This function computes the bounding hull (bounding box) of the ROI, determining the
    spatial extents in all dimensions (x, y, z, t, c).
    
    All vectors are expected to be 5D coordinates containing x, y, z, t, c values.
    
    Args:
        vectors: List of 5D vectors defining the ROI geometry (format depends on ROI kind)
                - Rectangle: 2 corners (opposite corners of rectangle)
                - Ellipse: center point and radii definition
                - Polygon/Line: edge/line points
                - Cube: corner points defining 3D box
        kind: The kind of ROI (from RoiKindChoices enum)
        
    Returns:
        ROIBounds object containing min/max coordinates for each dimension
    """
    if not vectors:
        return ROIBounds()
    
    # Handle different ROI kinds with specific geometric interpretations
    if kind == enums.RoiKindChoices.RECTANGLE.value:
        return _calculate_rectangle_bounds(vectors)
    elif kind == enums.RoiKindChoices.POLYGON.value:
        return _calculate_polygon_bounds(vectors)
    elif kind == enums.RoiKindChoices.ELLIPSIS.value:
        return _calculate_ellipse_bounds(vectors)
    elif kind == enums.RoiKindChoices.LINE.value:
        return _calculate_line_bounds(vectors)
    elif kind == enums.RoiKindChoices.POINT.value:
        return _calculate_point_bounds(vectors)
    elif kind == enums.RoiKindChoices.PATH.value:
        return _calculate_path_bounds(vectors)
    elif kind == enums.RoiKindChoices.CUBE.value:
        return _calculate_cube_bounds(vectors)
    elif kind == enums.RoiKindChoices.SPECTRAL_RECTANGLE.value:
        return _calculate_spectral_rectangle_bounds(vectors)
    elif kind == enums.RoiKindChoices.TEMPORAL_RECTANGLE.value:
        return _calculate_temporal_rectangle_bounds(vectors)
    elif kind == enums.RoiKindChoices.SPECTRAL_CUBE.value:
        return _calculate_spectral_cube_bounds(vectors)
    elif kind == enums.RoiKindChoices.TEMPORAL_CUBE.value:
        return _calculate_temporal_cube_bounds(vectors)
    elif kind == enums.RoiKindChoices.HYPERCUBE.value:
        return _calculate_hypercube_bounds(vectors)
    elif kind == enums.RoiKindChoices.SPECTRAL_HYPERCUBE.value:
        return _calculate_spectral_hypercube_bounds(vectors)
    elif kind == enums.RoiKindChoices.FRAME.value:
        return _calculate_frame_bounds(vectors)
    elif kind == enums.RoiKindChoices.SLICE.value:
        return _calculate_slice_bounds(vectors)
    else:
        # For unknown ROI types, try to extract coordinates from vectors
        return _calculate_generic_bounds(vectors)


def _calculate_rectangle_bounds(vectors: List[Any]) -> ROIBounds:
    """
    Calculate bounds for a rectangular ROI.
    Rectangle vectors define 2 opposite corners of the rectangle.
    """
    if len(vectors) < 2:
        return ROIBounds()
    
    # For rectangle, we expect 2 corners defining opposite corners
    coords = _extract_coordinates(vectors[:2])
    return _bounds_from_coordinates(coords)


def _calculate_polygon_bounds(vectors: List[Any]) -> ROIBounds:
    """
    Calculate bounds for a polygonal ROI.
    Polygon vectors define the edge points of the polygon.
    """
    if not vectors:
        return ROIBounds()
    
    # For polygon, all points define the edges
    coords = _extract_coordinates(vectors)
    return _bounds_from_coordinates(coords)


def _calculate_ellipse_bounds(vectors: List[Any]) -> ROIBounds:
    """
    Calculate bounds for an elliptical ROI.
    Ellipse vectors: [center, radii_vector] where radii_vector defines r1, r2.
    """
    if len(vectors) < 2:
        return ROIBounds()
    
    # Extract center coordinates: [c, t, z, y, x]
    center_coords = _extract_coordinates([vectors[0]])
    cx, cy, cz, ct, cc = center_coords[0]
    
    # Extract radii from second vector: [c, t, z, y, x] where y=r2, x=r1
    if isinstance(vectors[1], (list, tuple)) and len(vectors[1]) >= 5:
        _, _, _, r2, r1 = vectors[1][:5]
    else:
        r1 = r2 = 0
    
    # Calculate ellipse bounds (axis-aligned)
    return ROIBounds(
        min_x=int(cx - r1), max_x=int(cx + r1),
        min_y=int(cy - r2), max_y=int(cy + r2),
        min_z=int(cz), max_z=int(cz),
        min_t=int(ct), max_t=int(ct),
        min_c=int(cc), max_c=int(cc)
    )


def _calculate_line_bounds(vectors: List[Any]) -> ROIBounds:
    """
    Calculate bounds for a line ROI.
    Line vectors define the points along the line.
    """
    if not vectors:
        return ROIBounds()
    
    # For line, all points define the line path
    coords = _extract_coordinates(vectors)
    return _bounds_from_coordinates(coords)


def _calculate_point_bounds(vectors: List[Any]) -> ROIBounds:
    """
    Calculate bounds for a point ROI.
    Point vectors define a single point location.
    """
    if not vectors:
        return ROIBounds()
    
    # For point, we expect a single coordinate
    coords = _extract_coordinates([vectors[0]])
    point = coords[0]
    
    return ROIBounds(
        min_x=int(point[0]), max_x=int(point[0]),
        min_y=int(point[1]), max_y=int(point[1]),
        min_z=int(point[2]), max_z=int(point[2]),
        min_t=int(point[3]), max_t=int(point[3]),
        min_c=int(point[4]), max_c=int(point[4])
    )


def _calculate_path_bounds(vectors: List[Any]) -> ROIBounds:
    """
    Calculate bounds for a path ROI (sequence of connected points).
    Path vectors define the sequence of points along the path.
    """
    return _calculate_polygon_bounds(vectors)  # Same logic as polygon


def _calculate_cube_bounds(vectors: List[Any]) -> ROIBounds:
    """
    Calculate bounds for a cubic ROI (XYZ).
    Cube vectors define corner points of the 3D box.
    """
    if not vectors:
        return ROIBounds()
    
    # For cube, we expect corner points defining the 3D box
    coords = _extract_coordinates(vectors)
    return _bounds_from_coordinates(coords)


def _calculate_spectral_rectangle_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for a spectral rectangular ROI (XYC)."""
    return _calculate_rectangle_bounds(vectors)


def _calculate_temporal_rectangle_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for a temporal rectangular ROI (XYT)."""
    return _calculate_rectangle_bounds(vectors)


def _calculate_spectral_cube_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for a spectral cubic ROI (XYZC)."""
    return _calculate_cube_bounds(vectors)


def _calculate_temporal_cube_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for a temporal cubic ROI (XYZT)."""
    return _calculate_cube_bounds(vectors)


def _calculate_hypercube_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for a hypercube ROI (XYZT)."""
    return _calculate_cube_bounds(vectors)


def _calculate_spectral_hypercube_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for a spectral hypercube ROI (XYZTC)."""
    return _calculate_cube_bounds(vectors)


def _calculate_frame_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for a frame ROI."""
    return _calculate_rectangle_bounds(vectors)


def _calculate_slice_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for a slice ROI."""
    return _calculate_rectangle_bounds(vectors)


def _calculate_generic_bounds(vectors: List[Any]) -> ROIBounds:
    """Calculate bounds for unknown ROI types by extracting all coordinate information."""
    if not vectors:
        return ROIBounds()
    
    # For generic/unknown types, extract all coordinates
    coords = _extract_coordinates(vectors)
    return _bounds_from_coordinates(coords)


def update_roi_bounds(roi_instance: "ROI") -> None:
    """
    Update the min/max coordinate fields of an ROI instance based on its vectors and kind.
    
    Args:
        roi_instance: An instance of the ROI model
    """
    bounds = calculate_roi_bounds(roi_instance.vectors, roi_instance.kind)
    
    # Update the instance fields
    roi_instance.min_x = bounds.min_x
    roi_instance.max_x = bounds.max_x
    roi_instance.min_y = bounds.min_y  
    roi_instance.max_y = bounds.max_y
    roi_instance.min_z = bounds.min_z
    roi_instance.max_z = bounds.max_z
    roi_instance.min_t = bounds.min_t
    roi_instance.max_t = bounds.max_t
    roi_instance.min_c = bounds.min_c
    roi_instance.max_c = bounds.max_c
