#!/usr/bin/env python
"""
Demo script showing the corrected ROI bounds calculation with 5D coordinates.

This demonstrates the proper vector format: [c, t, z, y, x] and how different ROI types work.
"""

from core.logic.roi import calculate_roi_bounds
from core import enums


def demo_rectangle():
    """Demonstrate rectangle ROI with 5D coordinates."""
    print("=== Rectangle ROI Demo ===")
    print("Rectangle defined by 2 opposite corners")
    
    # Two corners of a rectangle: [c, t, z, y, x]
    vectors = [
        [0, 1, 5, 20, 10],  # Corner 1: channel=0, time=1, z=5, y=20, x=10
        [2, 3, 15, 80, 50]  # Corner 2: channel=2, time=3, z=15, y=80, x=50
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.RECTANGLE.value)
    print(f"Input vectors: {vectors}")
    print(f"Calculated bounds:")
    print(f"  X: {bounds.min_x} to {bounds.max_x} (width: {bounds.width})")
    print(f"  Y: {bounds.min_y} to {bounds.max_y} (height: {bounds.height})")
    print(f"  Z: {bounds.min_z} to {bounds.max_z} (depth: {bounds.depth})")
    print(f"  T: {bounds.min_t} to {bounds.max_t} (duration: {bounds.duration})")
    print(f"  C: {bounds.min_c} to {bounds.max_c} (channels: {bounds.channels})")
    print(f"  Area: {bounds.area}, Volume: {bounds.volume}")
    print()


def demo_ellipse():
    """Demonstrate ellipse ROI with center and radii."""
    print("=== Ellipse ROI Demo ===")
    print("Ellipse defined by center and radii vector")
    
    # Center point and radii: [c, t, z, y, x]
    vectors = [
        [1, 2, 10, 50, 100],  # Center: channel=1, time=2, z=10, y=50, x=100
        [0, 0, 0, 20, 30]     # Radii: r_y=20, r_x=30
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.ELLIPSIS.value)
    print(f"Center: {vectors[0]}")
    print(f"Radii: {vectors[1]} (r_y=20, r_x=30)")
    print(f"Calculated bounds:")
    print(f"  X: {bounds.min_x} to {bounds.max_x} (width: {bounds.width})")
    print(f"  Y: {bounds.min_y} to {bounds.max_y} (height: {bounds.height})")
    print(f"  Z: {bounds.min_z} to {bounds.max_z}")
    print(f"  T: {bounds.min_t} to {bounds.max_t}")
    print(f"  C: {bounds.min_c} to {bounds.max_c}")
    print()


def demo_polygon():
    """Demonstrate polygon ROI with edge points."""
    print("=== Polygon ROI Demo ===")
    print("Polygon defined by edge points")
    
    # Polygon vertices: [c, t, z, y, x]
    vectors = [
        [0, 0, 5, 0, 0],      # Vertex 1
        [0, 0, 5, 50, 100],   # Vertex 2
        [0, 0, 5, 150, 75],   # Vertex 3
        [0, 0, 5, 125, 25],   # Vertex 4
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.POLYGON.value)
    print(f"Vertices: {vectors}")
    print(f"Calculated bounds:")
    print(f"  X: {bounds.min_x} to {bounds.max_x} (width: {bounds.width})")
    print(f"  Y: {bounds.min_y} to {bounds.max_y} (height: {bounds.height})")
    print(f"  Z: {bounds.min_z} to {bounds.max_z}")
    print(f"  All vertices at same time and channel")
    print()


def demo_line():
    """Demonstrate line ROI with line points."""
    print("=== Line ROI Demo ===")
    print("Line defined by multiple points")
    
    # Line points: [c, t, z, y, x]
    vectors = [
        [1, 5, 8, 10, 20],    # Start point
        [1, 5, 8, 50, 80],    # End point
        [1, 5, 8, 90, 140],   # Additional point for polyline
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.LINE.value)
    print(f"Line points: {vectors}")
    print(f"Calculated bounds:")
    print(f"  X: {bounds.min_x} to {bounds.max_x} (width: {bounds.width})")
    print(f"  Y: {bounds.min_y} to {bounds.max_y} (height: {bounds.height})")
    print(f"  Z: {bounds.min_z} to {bounds.max_z}")
    print(f"  T: {bounds.min_t} to {bounds.max_t}")
    print(f"  C: {bounds.min_c} to {bounds.max_c}")
    print()


def demo_cube():
    """Demonstrate cube ROI with corner points."""
    print("=== Cube ROI Demo ===")
    print("Cube defined by corner points")
    
    # Cube corners: [c, t, z, y, x]
    vectors = [
        [0, 1, 10, 20, 30],   # Corner 1
        [0, 1, 50, 80, 120],  # Corner 2 (opposite)
    ]
    
    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.CUBE.value)
    print(f"Cube corners: {vectors}")
    print(f"Calculated bounds:")
    print(f"  X: {bounds.min_x} to {bounds.max_x} (width: {bounds.width})")
    print(f"  Y: {bounds.min_y} to {bounds.max_y} (height: {bounds.height})")
    print(f"  Z: {bounds.min_z} to {bounds.max_z} (depth: {bounds.depth})")
    print(f"  T: {bounds.min_t} to {bounds.max_t}")
    print(f"  C: {bounds.min_c} to {bounds.max_c}")
    print(f"  Volume: {bounds.volume}")
    print()


if __name__ == "__main__":
    print("ROI Bounds Calculation Demo - 5D Coordinates [c, t, z, y, x]")
    print("=" * 60)
    print()
    
    demo_rectangle()
    demo_ellipse()
    demo_polygon()
    demo_line()
    demo_cube()
    
    print("Demo completed successfully!")
