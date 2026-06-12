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


def test_legacy_order_argument_removed():
    sdl = schema.as_str()
    images_def = sdl[sdl.find("images(") : sdl.find(")", sdl.find("images("))]
    assert "ordering:" in images_def
    assert "order:" not in images_def
