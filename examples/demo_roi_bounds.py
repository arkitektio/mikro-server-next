#!/usr/bin/env python3
"""
Demonstration script for ROI bounds calculation functionality.

This script shows how to use the calculate_roi_bounds function and the 
ROI.calculate_bounds() method for different types of ROIs.
"""

from core.logic.roi import calculate_roi_bounds
from core import enums


def demo_rectangle_roi():
    """Demonstrate rectangle ROI bounds calculation."""
    print("=== Rectangle ROI ===")
    vectors = [
        {'x': 10, 'y': 20},
        {'x': 50, 'y': 80}
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.RECTANGLE.value)
    
    print(f"Vectors: {vectors}")
    print(f"Bounds: {bounds}")
    print(f"Width: {bounds.width}")
    print(f"Height: {bounds.height}")
    print(f"Area: {bounds.area}")
    print()


def demo_polygon_roi():
    """Demonstrate polygon ROI bounds calculation."""
    print("=== Polygon ROI ===")
    # Triangle
    vectors = [
        {'x': 0, 'y': 0},
        {'x': 100, 'y': 50},
        {'x': 50, 'y': 150}
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.POLYGON.value)
    
    print(f"Vectors: {vectors}")
    print(f"Bounds: {bounds}")
    print(f"Bounding box area: {bounds.area}")
    print()


def demo_cube_roi():
    """Demonstrate 3D cube ROI bounds calculation."""
    print("=== 3D Cube ROI ===")
    vectors = [
        {'x': 10, 'y': 20, 'z': 5},
        {'x': 50, 'y': 80, 'z': 25}
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.CUBE.value)
    
    print(f"Vectors: {vectors}")
    print(f"Bounds: {bounds}")
    print(f"Volume: {bounds.volume}")
    print()


def demo_spectral_hypercube_roi():
    """Demonstrate 5D spectral hypercube ROI bounds calculation."""
    print("=== Spectral Hypercube ROI (5D) ===")
    vectors = [
        {'x': 0, 'y': 0, 'z': 0, 't': 0, 'c': 0},
        {'x': 100, 'y': 200, 'z': 50, 't': 10, 'c': 3}
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.SPECTRAL_HYPERCUBE.value)
    
    print(f"Vectors: {vectors}")
    print(f"Bounds: {bounds}")
    print(f"X range: {bounds.min_x} to {bounds.max_x}")
    print(f"Y range: {bounds.min_y} to {bounds.max_y}")
    print(f"Z range: {bounds.min_z} to {bounds.max_z}")
    print(f"T range: {bounds.min_t} to {bounds.max_t}")
    print(f"C range: {bounds.min_c} to {bounds.max_c}")
    print(f"Total volume: {bounds.volume}")
    print(f"Duration: {bounds.duration}")
    print(f"Channels: {bounds.channels}")
    print()


def demo_ellipse_roi():
    """Demonstrate ellipse ROI bounds calculation."""
    print("=== Ellipse ROI ===")
    vectors = [
        {'x': 50, 'y': 60},  # center
        {'x': 25, 'y': 0},   # semi-major axis
        {'x': 15, 'y': 0}    # semi-minor axis
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.ELLIPSIS.value)
    
    print(f"Vectors: {vectors}")
    print(f"Center: ({vectors[0]['x']}, {vectors[0]['y']})")
    print(f"Semi-major axis: {vectors[1]['x']}")
    print(f"Semi-minor axis: {vectors[2]['x']}")
    print(f"Bounds: {bounds}")
    print()


def demo_list_format_vectors():
    """Demonstrate bounds calculation with list-format vectors."""
    print("=== List Format Vectors ===")
    vectors = [
        [10, 20, 5, 0, 1],  # [x, y, z, t, c]
        [50, 80, 25, 5, 3]
    ]
    
    bounds = calculate_roi_bounds(vectors, "unknown_type")
    
    print(f"Vectors: {vectors}")
    print(f"Bounds: {bounds}")
    print("Note: This works for any vector format and unknown ROI types!")
    print()


if __name__ == "__main__":
    print("ROI Bounds Calculation Demo")
    print("=" * 40)
    print()
    
    demo_rectangle_roi()
    demo_polygon_roi() 
    demo_cube_roi()
    demo_spectral_hypercube_roi()
    demo_ellipse_roi()
    demo_list_format_vectors()
    
    print("=" * 40)
    print("Demo completed!")
    print()
    print("Usage in Django models:")
    print("1. Call calculate_roi_bounds(vectors, kind) directly")
    print("2. Use roi_instance.calculate_bounds() method on ROI objects")
    print("3. The bounds will be automatically calculated and can be used for:")
    print("   - Spatial indexing and queries")
    print("   - Collision detection")
    print("   - Visualization bounds")
    print("   - ROI intersection analysis")
