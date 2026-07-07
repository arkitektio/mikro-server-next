"""Schema smoke tests: the schema must build and expose the expected
filter inputs and ordering arguments. No database required."""

from mikro_server.schema import schema


def test_schema_builds():
    sdl = schema.as_str()
    assert sdl


def test_filter_inputs_exist():
    sdl = schema.as_str()
    for input_name in [
        "input ImageFilter",
        "input DatasetFilter",
        "input FileFilter",
        "input ROIFilter",
    ]:
        assert input_name in sdl, f"{input_name} missing from schema"


def test_images_query_has_filters():
    images_field = schema.query.__strawberry_definition__.fields
    field = next(f for f in images_field if f.name == "images")
    arg_names = {arg.python_name for arg in field.arguments}
    assert "filters" in arg_names
    assert "ordering" in arg_names


def test_order_inputs_exist():
    sdl = schema.as_str()
    for input_name in [
        "input ImageOrder",
        "input DatasetOrder",
        "input FileOrder",
        "input ROIOrder",
        "input RenderTreeOrder",
        "input FileViewOrder",
    ]:
        assert input_name in sdl, f"{input_name} missing from schema"


def test_layer_render_graph_surface_exists():
    """The composable in-layer render graph is exposed for input, output and helpers."""
    sdl = schema.as_str()
    for token in [
        "interface LayerRenderNode",
        "type ChannelSourceNode",
        "type BlendNode",
        "type LayerRenderGraph",
        "input LayerNodeInput",
        "input LayerRenderGraphInput",
        "renderGraph",
        "createRgbLayer",
        "createIntensityLayer",
        "createLabelLayer",
        "type ProjectionNode",
        "enum ProjectionMode",
        "createVolumeLayer",
    ]:
        assert token in sdl, f"{token} missing from schema"


def test_polymorphic_layer_subtypes_exist():
    """All the polymorphic Layer subtypes implement the Layer interface."""
    sdl = schema.as_str()
    for token in [
        "type ImageLayer implements Layer",
        "type ShapeLayer implements Layer",
        "type PointLayer implements Layer",
        "type TrackLayer implements Layer",
        "type MeshLayer implements Layer",
    ]:
        assert token in sdl, f"{token} missing from schema"


def test_layer_alpha_compositing_fields_exist():
    """The polymorphic Layer interface carries the neuroglancer-style alpha compositing knobs."""
    sdl = schema.as_str()
    layer_def = sdl[sdl.find("interface Layer ") : sdl.find("}", sdl.find("interface Layer "))]
    for field in ["blending:", "opacity:", "visible:", "order:"]:
        assert field in layer_def, f"Layer.{field} missing from interface"
    # The ImageLayer carries its data source and the render graph; all rendering
    # (colormap/contrast/gamma) now lives inside the render graph, not on flat fields.
    image_def = sdl[sdl.find("type ImageLayer implements") : sdl.find("}", sdl.find("type ImageLayer implements"))]
    for field in ["lens:", "renderGraph:"]:
        assert field in image_def, f"ImageLayer.{field} missing"
    for field in ["gamma:", "colormap:", "climMin:", "climMax:", "color:"]:
        assert field not in image_def, f"vestigial flat render field ImageLayer.{field} should be gone (moved into the render graph)"
    # The NORMAL (alpha-over) blend mode must be available.
    blending_def = sdl[sdl.find("enum Blending ") : sdl.find("}", sdl.find("enum Blending "))]
    assert "NORMAL" in blending_def


def test_layer_is_polymorphic_interface():
    """Layer is a GraphQL interface implemented by ImageLayer (and future subtypes)."""
    sdl = schema.as_str()
    assert "interface Layer " in sdl
    assert "type ImageLayer implements Layer" in sdl


def test_blending_enums_stay_in_sync():
    """The GraphQL Blending enum values must be a subset of the DB BlendingChoices."""
    from core import enums

    graphql_values = {member.value for member in enums.Blending}
    db_values = set(enums.BlendingChoices.values)
    assert graphql_values <= db_values, graphql_values - db_values


def test_legacy_order_argument_removed():
    sdl = schema.as_str()
    images_def = sdl[sdl.find("images(") : sdl.find(")", sdl.find("images("))]
    assert "ordering:" in images_def
    assert "order:" not in images_def
