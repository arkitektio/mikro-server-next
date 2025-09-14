"""
Test cases for ROI bounds calculation functionality.
"""
import pytest
from core.logic.roi import calculate_roi_bounds, ROIBounds
from core import enums


class TestROIBoundsCalculation:
    """Test cases for calculate_roi_bounds function."""

    def test_rectangle_bounds(self):
        """Test bounds calculation for rectangular ROI."""
        vectors = [
            [0, 1, 5, 20, 10],  # [c, t, z, y, x] - first corner
            [2, 2, 15, 80, 50]  # [c, t, z, y, x] - opposite corner
        ]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.RECTANGLE.value)
        
        assert bounds.min_x == 10
        assert bounds.max_x == 50
        assert bounds.min_y == 20
        assert bounds.max_y == 80
        assert bounds.min_z == 5
        assert bounds.max_z == 15
        assert bounds.min_t == 1
        assert bounds.max_t == 2
        assert bounds.min_c == 0
        assert bounds.max_c == 2
        assert bounds.width == 40
        assert bounds.height == 60
        assert bounds.area == 2400

    def test_polygon_bounds(self):
        """Test bounds calculation for polygonal ROI."""
        vectors = [
            [1, 0, 3, 0, 0],    # [c, t, z, y, x] - polygon vertices
            [1, 0, 3, 50, 100], # [c, t, z, y, x]
            [1, 0, 3, 150, 75], # [c, t, z, y, x]
            [1, 0, 3, 125, 25]  # [c, t, z, y, x]
        ]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.POLYGON.value)
        
        assert bounds.min_x == 0
        assert bounds.max_x == 100
        assert bounds.min_y == 0
        assert bounds.max_y == 150
        assert bounds.min_z == 3
        assert bounds.max_z == 3

    def test_point_bounds(self):
        """Test bounds calculation for point ROI."""
        vectors = [[1, 5, 8, 37, 42]]  # [c, t, z, y, x]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.POINT.value)
        
        assert bounds.min_x == 42
        assert bounds.max_x == 42
        assert bounds.min_y == 37
        assert bounds.max_y == 37
        assert bounds.min_z == 8
        assert bounds.max_z == 8
        assert bounds.min_t == 5
        assert bounds.max_t == 5
        assert bounds.min_c == 1
        assert bounds.max_c == 1

    def test_cube_bounds(self):
        """Test bounds calculation for cubic ROI."""
        vectors = [
            {'x': 10, 'y': 20, 'z': 5},
            {'x': 50, 'y': 80, 'z': 25}
        ]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.CUBE.value)
        
        assert bounds.min_x == 10
        assert bounds.max_x == 50
        assert bounds.min_y == 20
        assert bounds.max_y == 80
        assert bounds.min_z == 5
        assert bounds.max_z == 25
        assert bounds.volume == 48000

    def test_spectral_hypercube_bounds(self):
        """Test bounds calculation for spectral hypercube ROI."""
        vectors = [
            {'x': 0, 'y': 0, 'z': 0, 't': 0, 'c': 0},
            {'x': 100, 'y': 200, 'z': 50, 't': 10, 'c': 3}
        ]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.SPECTRAL_HYPERCUBE.value)
        
        assert bounds.min_x == 0
        assert bounds.max_x == 100
        assert bounds.min_y == 0
        assert bounds.max_y == 200
        assert bounds.min_z == 0
        assert bounds.max_z == 50
        assert bounds.min_t == 0
        assert bounds.max_t == 10
        assert bounds.min_c == 0
        assert bounds.max_c == 3

    def test_line_bounds(self):
        """Test bounds calculation for line ROI."""
        vectors = [
            {'x': 25, 'y': 30},
            {'x': 75, 'y': 90}
        ]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.LINE.value)
        
        assert bounds.min_x == 25
        assert bounds.max_x == 75
        assert bounds.min_y == 30
        assert bounds.max_y == 90

    def test_ellipse_bounds(self):
        """Test bounds calculation for elliptical ROI."""
        vectors = [
            {'x': 50, 'y': 60},  # center
            {'x': 25, 'y': 0},   # semi-major axis
            {'x': 15, 'y': 0}    # semi-minor axis
        ]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.ELLIPSIS.value)
        
        assert bounds.min_x == 25  # 50 - 25
        assert bounds.max_x == 75  # 50 + 25
        assert bounds.min_y == 45  # 60 - 15
        assert bounds.max_y == 75  # 60 + 15

    def test_empty_vectors(self):
        """Test bounds calculation with empty vectors."""
        bounds = calculate_roi_bounds([], enums.RoiKindChoices.RECTANGLE.value)
        
        assert not bounds.has_bounds()
        assert bounds.min_x is None
        assert bounds.max_x is None
        assert bounds.min_y is None
        assert bounds.max_y is None

    def test_unknown_roi_kind(self):
        """Test bounds calculation for unknown ROI kind."""
        vectors = [
            {'x': 10, 'y': 20, 'z': 5},
            {'x': 50, 'y': 80, 'z': 25}
        ]
        bounds = calculate_roi_bounds(vectors, "unknown_type")
        
        assert bounds.min_x == 10
        assert bounds.max_x == 50
        assert bounds.min_y == 20
        assert bounds.max_y == 80
        assert bounds.min_z == 5
        assert bounds.max_z == 25

    def test_list_format_vectors(self):
        """Test bounds calculation with list format vectors."""
        vectors = [
            [10, 20, 5],  # [x, y, z]
            [50, 80, 25]
        ]
        bounds = calculate_roi_bounds(vectors, "unknown_type")
        
        assert bounds.min_x == 10
        assert bounds.max_x == 50
        assert bounds.min_y == 20
        assert bounds.max_y == 80
        assert bounds.min_z == 5
        assert bounds.max_z == 25

    def test_bounds_properties(self):
        """Test the convenience properties of ROIBounds."""
        vectors = [
            {'x': 10, 'y': 20, 'z': 5, 't': 0, 'c': 1},
            {'x': 50, 'y': 80, 'z': 25, 't': 10, 'c': 3}
        ]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.SPECTRAL_HYPERCUBE.value)
        
        assert bounds.width == 40
        assert bounds.height == 60
        assert bounds.depth == 20
        assert bounds.duration == 10
        assert bounds.channels == 3  # 3 - 1 + 1 = 3 channels
        assert bounds.area == 2400
        assert bounds.volume == 48000
        assert bounds.has_bounds() is True

    def test_to_dict_method(self):
        """Test the to_dict method for backward compatibility."""
        vectors = [
            {'x': 10, 'y': 20},
            {'x': 50, 'y': 80}
        ]
        bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.RECTANGLE.value)
        bounds_dict = bounds.to_dict()
        
        assert bounds_dict['min_x'] == 10
        assert bounds_dict['max_x'] == 50
        assert bounds_dict['min_y'] == 20
        assert bounds_dict['max_y'] == 80
        assert bounds_dict['min_z'] is None
