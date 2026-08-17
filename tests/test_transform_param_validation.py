"""The transform input union: the member is the kind, and nothing rides along.

An authored edge arrives as the flat ``TransformInput`` -- a ``kind`` plus the union of
every kind's parameter fields -- and is matched to a strict per-kind member model that
forbids what is not its own. So a parameter that contradicts the kind (a `translation`
on a SCALE edge, a `reason` on anything but UNMAPPABLE, axis names on a kind that acts
on every axis) is an **error naming both**, where it used to be silently dropped -- and
in the axes case silently *wrong*, because stored axis names override what
``edge_axis_names`` reports as the parameter ordering.

The same contract holds at every altitude: the parse layer for the API, and the
logic-layer writers (`build_registration_edge`, `write_relation_edge`) for callers below
it -- the tests here pin both, so removing either gate makes something fail. The member
inputs published under ``@unionElementOf`` are codegen's copy of the same truth.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext
from strawberry.types import ExecutionResult

from core import enums, models
from core.input_unions import parse_union_member
from core.inputs.coords import TRANSFORM_MEMBERS, FieldTransformInputModel, MapAxisTransformInputModel
from core.logic import graph as graph_logic
from mikro_server.schema import schema
from tests import seed

CREATE_TRANSFORM = """
mutation Create($input: CreateTransformationInput!) {
  createTransformation(input: $input) { id kind inputAxes outputAxes }
}
"""

UPDATE_TRANSFORM = """
mutation Update($input: UpdateTransformationInput!) {
  updateTransformation(input: $input) { id version }
}
"""

CREATE_CS = """
mutation CreateCS($input: CreateCoordinateSystemInput!) {
  createCoordinateSystem(input: $input) { id }
}
"""

WORLD_AXES = [
    {"name": "y", "type": "SPACE", "unit": "micrometer"},
    {"name": "x", "type": "SPACE", "unit": "micrometer"},
]


async def _dataset_and_world(ctx: HttpContext) -> tuple[str, str]:
    """A y/x dataset's intrinsic system, and a y/x world with nothing registered into it."""
    dataset = await seed.create_array_dataset(ctx, axes=seed.YX_AXES, shapes=[[64, 64]])
    intrinsic = await sync_to_async(lambda: dataset.coordinate_system.pk)()
    result = await schema.execute(CREATE_CS, context_value=ctx, variable_values={"input": {"name": "World", "axes": WORLD_AXES, "registrations": []}})
    assert not result.errors, result.errors
    return str(intrinsic), str(result.data["createCoordinateSystem"]["id"])


async def _create(ctx: HttpContext, input_id: str, output_id: str, transform: dict) -> ExecutionResult:
    return await schema.execute(
        CREATE_TRANSFORM,
        context_value=ctx,
        variable_values={"input": {"input": input_id, "output": output_id, "transform": transform}},
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transform", "phrase"),
    [
        # A parameter of some other member: named, not dropped.
        ({"kind": "SCALE", "scale": [1.0, 1.0], "translation": [1.0, 1.0]}, "A SCALE transformation does not read `translation`"),
        ({"kind": "SCALE", "scale": [1.0, 1.0], "affine": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]}, "A SCALE transformation does not read `affine`"),
        ({"kind": "TRANSLATION", "translation": [1.0, 1.0], "scale": [2.0, 2.0]}, "A TRANSLATION transformation does not read `scale`"),
        ({"kind": "AFFINE", "affine": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], "scale": [2.0, 2.0]}, "An AFFINE transformation does not read `scale`"),
        ({"kind": "ROTATION", "affine": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], "translation": [1.0, 1.0]}, "A ROTATION transformation does not read `translation`"),
        ({"kind": "MAP_AXIS", "inputAxes": ["y", "x"], "outputAxes": ["x", "y"], "scale": [1.0, 1.0]}, "A MAP_AXIS transformation does not read `scale`"),
        # IDENTITY reads nothing at all.
        ({"kind": "IDENTITY", "scale": [1.0, 1.0]}, "takes no parameters at all"),
        # Axis names on a kind that acts on every axis: the silently-wrong case.
        ({"kind": "SCALE", "scale": [1.0, 1.0], "inputAxes": ["y", "x"]}, "A SCALE transformation does not read `inputAxes`"),
        ({"kind": "AFFINE", "affine": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], "outputAxes": ["y", "x"]}, "An AFFINE transformation does not read `outputAxes`"),
        # `reason` belongs to UNMAPPABLE, `field` to FIELD.
        ({"kind": "SCALE", "scale": [1.0, 1.0], "reason": "because"}, "A SCALE transformation does not read `reason`"),
        ({"kind": "UNMAPPABLE", "scale": [1.0, 1.0]}, "An UNMAPPABLE transformation does not read `scale`"),
        # Missing the one parameter the kind requires.
        ({"kind": "SCALE"}, "A SCALE transformation requires `scale`"),
        ({"kind": "AFFINE"}, "An AFFINE transformation requires `affine`"),
        ({"kind": "ROTATION"}, "A ROTATION transformation requires `affine`"),
        ({"kind": "FIELD", "inputAxes": ["y", "x"], "outputAxes": ["y", "x"]}, "A FIELD transformation requires `field`"),
        ({"kind": "MAP_AXIS", "inputAxes": ["y", "x"]}, "A MAP_AXIS transformation requires `outputAxes`"),
        ({"kind": "BY_DIMENSION", "outputAxes": ["y"]}, "A BY_DIMENSION transformation requires `inputAxes`"),
    ],
)
async def test_a_parameter_that_contradicts_the_kind_is_an_error_not_a_drop(authenticated_context: HttpContext, transform: dict, phrase: str) -> None:
    """Every mismatch is named after both the kind and the field, and nothing is written."""
    intrinsic, world = await _dataset_and_world(authenticated_context)
    before = await sync_to_async(models.Transformation.objects.count)()

    result = await _create(authenticated_context, intrinsic, world, transform)

    assert result.errors, f"expected an error for {transform}"
    assert phrase in str(result.errors[0]), str(result.errors[0])
    assert await sync_to_async(models.Transformation.objects.count)() == before, "a refused edge must write nothing"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transform", "phrase"),
    [
        # A zero factor collapses its axis onto a point. `_scale_invariance` classifies a
        # scale by whether its entries are *equal*, so [0, 0] used to be reported as a
        # SIMILARITY -- angles and length ratios preserved -- for a map that preserves
        # nothing, and `is_invertible` is kind-only, so the client was then handed an
        # `inverted: true` step it could not honour.
        ({"kind": "SCALE", "scale": [0.0, 1.0]}, "no factor may be zero"),
        ({"kind": "SCALE", "scale": [0.0, 0.0]}, "no factor may be zero"),
        ({"kind": "BY_DIMENSION", "inputAxes": ["y", "x"], "outputAxes": ["y", "x"], "scale": [1.0, 0.0]}, "no factor may be zero"),
        # A row whose linear part is all zeros sends every input to one value. The last
        # column is the translation and is excluded: an offset does not un-collapse a row.
        ({"kind": "AFFINE", "affine": [[0.0, 0.0, 5.0], [0.0, 1.0, 0.0]]}, "no row's linear part may be all zeros"),
        ({"kind": "ROTATION", "affine": [[1.0, 0.0, 0.0], [0.0, 0.0, 0.0]]}, "no row's linear part may be all zeros"),
    ],
)
async def test_a_map_that_collapses_an_axis_is_refused(authenticated_context: HttpContext, transform: dict, phrase: str) -> None:
    """The value rules, at the API altitude. Only a collapse -- never a merely odd number."""
    intrinsic, world = await _dataset_and_world(authenticated_context)
    before = await sync_to_async(models.Transformation.objects.count)()

    result = await _create(authenticated_context, intrinsic, world, transform)

    assert result.errors, f"expected an error for {transform}"
    assert phrase in str(result.errors[0]), str(result.errors[0])
    assert await sync_to_async(models.Transformation.objects.count)() == before, "a refused edge must write nothing"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_refinement_cannot_collapse_an_axis_either(authenticated_context: HttpContext) -> None:
    """`updateTransformation` gates values exactly as creation does, and nearly did not.

    It is the one write that reaches neither gate on its own: its parameters arrive flat --
    there is no `TransformInput`, so the union members' validators never run -- and it
    assembles its params dict by hand rather than through `_assemble_edge_params`. Refining
    a good SCALE edge to `[0, 0]` was the way left to store a collapsing map.
    """
    ctx = authenticated_context
    intrinsic, world = await _dataset_and_world(ctx)

    result = await _create(ctx, intrinsic, world, {"kind": "SCALE", "scale": [0.5, 0.5]})
    assert not result.errors, result.errors
    edge_id = result.data["createTransformation"]["id"]

    result = await schema.execute(UPDATE_TRANSFORM, context_value=ctx, variable_values={"input": {"id": edge_id, "scale": [0.0, 0.5]}})
    assert result.errors and "no factor may be zero" in str(result.errors[0]), str(result.errors and result.errors[0])

    edge = await sync_to_async(models.Transformation.objects.get)(pk=edge_id)
    assert edge.params == {"scale": [0.5, 0.5]} and edge.version == 1, "a refused refinement writes nothing and bumps nothing"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_mirrored_axis_and_an_offset_of_zero_are_left_alone(authenticated_context: HttpContext) -> None:
    """The boundary of the rule above: a negative factor is a flip, and zero is an offset.

    A sign flip cannot produce a stored `min > max` -- `form_interval` takes min/max per
    term and `transformed_bbox` enumerates every corner -- so there is nothing to protect
    against, and refusing it would refuse a real acquisition geometry.
    """
    intrinsic, world = await _dataset_and_world(authenticated_context)

    result = await _create(authenticated_context, intrinsic, world, {"kind": "SCALE", "scale": [-1.0, 1.0]})
    assert not result.errors, result.errors

    result = await _create(authenticated_context, intrinsic, world, {"kind": "TRANSLATION", "translation": [0.0, 0.0]})
    assert not result.errors, result.errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_per_axis_edge_cannot_cross_a_rank_boundary(authenticated_context: HttpContext) -> None:
    """A scale carries one number per input axis, so its matrix is square at that rank.

    Only the *input* rank was checked, so a two-entry scale from a (y,x) grid into a
    four-axis world was written without complaint -- and surfaced nowhere near its author:
    `to_matrix` raises `NonAffineTransformError`, which the extent walk swallows into
    `ExtentState.NON_AFFINE`, leaving the source unboundable in every spatial query over
    that space forever.

    An AFFINE is deliberately *not* held to this: its matrix is M x (N+1) and rectangular
    by design, which is exactly how a rank-crossing edge is written.
    """
    ctx = authenticated_context
    dataset = await seed.create_array_dataset(ctx, axes=seed.YX_AXES, shapes=[[64, 64]])
    intrinsic = await sync_to_async(lambda: str(dataset.coordinate_system.pk))()

    big = await schema.execute(
        CREATE_CS,
        context_value=ctx,
        variable_values={"input": {"name": "Big", "axes": [{"name": "t", "type": "TIME", "unit": "second"}, {"name": "z", "type": "SPACE", "unit": "micrometer"}, *WORLD_AXES], "registrations": []}},
    )
    assert not big.errors, big.errors
    world = str(big.data["createCoordinateSystem"]["id"])

    result = await _create(ctx, intrinsic, world, {"kind": "SCALE", "scale": [0.1, 0.1]})
    assert result.errors and "relates spaces of equal rank" in str(result.errors[0]), str(result.errors and result.errors[0])

    # The same pair, said the way the model provides for: name the axes it acts on.
    result = await _create(ctx, intrinsic, world, {"kind": "BY_DIMENSION", "inputAxes": ["y", "x"], "outputAxes": ["y", "x"], "scale": [0.1, 0.1]})
    assert not result.errors, result.errors

    # And a whole matrix crosses ranks unbothered: 4 rows out, 2+1 columns in.
    result = await _create(ctx, intrinsic, world, {"kind": "AFFINE", "affine": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]})
    assert result.errors and "all zeros" in str(result.errors[0]), "the zero rows are caught, not the rank"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_scale_edge_also_gets_a_field_named_as_not_its_own(authenticated_context: HttpContext) -> None:
    """`field` is the FIELD member's alone; on any other kind it is a named stray."""
    intrinsic, world = await _dataset_and_world(authenticated_context)
    result = await _create(authenticated_context, intrinsic, world, {"kind": "SCALE", "scale": [1.0, 1.0], "field": world})
    assert result.errors and "A SCALE transformation does not read `field`" in str(result.errors[0]), str(result.errors and result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_wrapper_kinds_are_not_in_the_creatable_enum(authenticated_context: HttpContext) -> None:
    """SEQUENCE and BIJECTION are unrepresentable in TransformInput, not merely refused.

    The ingest builds them together with their children; a client naming one gets an enum
    coercion error before any resolver runs. The logic-layer gate for internal callers is
    pinned separately below.
    """
    intrinsic, world = await _dataset_and_world(authenticated_context)
    for kind in ("SEQUENCE", "BIJECTION"):
        result = await _create(authenticated_context, intrinsic, world, {"kind": kind})
        assert result.errors, f"{kind} must not be creatable"
        assert "CreatableTransformKind" in str(result.errors[0]), str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_registration_entry_is_validated_like_a_transformation(authenticated_context: HttpContext) -> None:
    """`registrations` lowers through the same union, so the same strays are refused."""
    dataset = await seed.create_array_dataset(authenticated_context, axes=seed.YX_AXES, shapes=[[64, 64]])
    dataset_id = str(dataset.pk)

    result = await schema.execute(
        CREATE_CS,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "name": "World",
                "axes": WORLD_AXES,
                "registrations": [{"dataset": dataset_id, "transform": {"kind": "SCALE", "scale": [1.0, 1.0], "translation": [2.0, 2.0]}}],
            }
        },
    )
    assert result.errors and "A SCALE transformation does not read `translation`" in str(result.errors[0]), str(result.errors and result.errors[0])
    assert not await sync_to_async(models.CoordinateSystem.objects.filter(name="World").exists)(), "a refused registration must roll the space back with it"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_omitted_transform_registers_an_identity(authenticated_context: HttpContext) -> None:
    """Omitting `transform` on a registration entry means IDENTITY, as the docs promise."""
    dataset = await seed.create_array_dataset(authenticated_context, axes=seed.YX_AXES, shapes=[[64, 64]])
    intrinsic = await sync_to_async(lambda: dataset.coordinate_system.pk)()

    result = await schema.execute(
        CREATE_CS,
        context_value=authenticated_context,
        variable_values={"input": {"name": "World", "axes": WORLD_AXES, "registrations": [{"dataset": str(dataset.pk)}]}},
    )
    assert not result.errors, result.errors

    edge = await sync_to_async(models.Transformation.objects.get)(input_id=intrinsic, output_id=result.data["createCoordinateSystem"]["id"])
    assert edge.kind == enums.TransformKindChoices.IDENTITY.value
    assert edge.params == {}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_each_member_persists_exactly_its_own_shape(authenticated_context: HttpContext) -> None:
    """The row holds what the kind reads: params for the metric kinds, axes only for the axis kinds."""
    ctx = authenticated_context

    intrinsic, world = await _dataset_and_world(ctx)
    result = await _create(ctx, intrinsic, world, {"kind": "SCALE", "scale": [0.5, 0.5]})
    assert not result.errors, result.errors
    edge = await sync_to_async(models.Transformation.objects.get)(pk=result.data["createTransformation"]["id"])
    assert edge.params == {"scale": [0.5, 0.5]}
    assert edge.input_axes is None and edge.output_axes is None, "a metric edge stores no axis names: stored names would override the systems' ordering"

    result = await _create(ctx, world, world, {"kind": "MAP_AXIS", "inputAxes": ["y", "x"], "outputAxes": ["x", "y"]})
    assert not result.errors, result.errors
    edge = await sync_to_async(models.Transformation.objects.get)(pk=result.data["createTransformation"]["id"])
    assert edge.params == {} and edge.input_axes == ["y", "x"] and edge.output_axes == ["x", "y"]

    result = await _create(ctx, intrinsic, world, {"kind": "BY_DIMENSION", "inputAxes": ["y", "x"], "outputAxes": ["y", "x"], "affine": [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0]]})
    assert not result.errors, result.errors
    edge = await sync_to_async(models.Transformation.objects.get)(pk=result.data["createTransformation"]["id"])
    assert edge.params == {"affine": [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0]]}, "a BY_DIMENSION's optional matrix rides in params"

    result = await _create(ctx, intrinsic, world, {"kind": "UNMAPPABLE", "reason": "one row per object"})
    assert not result.errors, result.errors
    edge = await sync_to_async(models.Transformation.objects.get)(pk=result.data["createTransformation"]["id"])
    assert edge.params == {"reason": "one row per object"} and edge.input_axes is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_refinement_must_match_the_edges_kind(authenticated_context: HttpContext) -> None:
    """`updateTransformation` gates parameters exactly as creation does.

    Before this gate a stray `affine` merged onto any edge was stored, never read by
    `to_matrix` -- and on a childless composite it demoted the reported invariance,
    because `invariance_of` classifies those by params keys.
    """
    ctx = authenticated_context
    intrinsic, world = await _dataset_and_world(ctx)
    result = await _create(ctx, intrinsic, world, {"kind": "SCALE", "scale": [0.5, 0.5]})
    assert not result.errors, result.errors
    edge_id = result.data["createTransformation"]["id"]

    result = await schema.execute(UPDATE_TRANSFORM, context_value=ctx, variable_values={"input": {"id": edge_id, "translation": [1.0, 1.0]}})
    assert result.errors and "A SCALE transformation does not read `translation`" in str(result.errors[0]), str(result.errors and result.errors[0])
    assert "refining it would write a number nothing reads" in str(result.errors[0])

    result = await schema.execute(UPDATE_TRANSFORM, context_value=ctx, variable_values={"input": {"id": edge_id, "scale": [0.51, 0.51]}})
    assert not result.errors, result.errors
    edge = await sync_to_async(models.Transformation.objects.get)(pk=edge_id)
    assert edge.params == {"scale": [0.51, 0.51]}
    assert edge.version == 2, "the refused refinement must not have bumped the version; the accepted one must"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_wrapper_refuses_refinement_toward_its_children(authenticated_context: HttpContext) -> None:
    """A SEQUENCE's parameters live on its children, and the update mutation says so."""
    ctx = authenticated_context
    intrinsic, world = await _dataset_and_world(ctx)

    def build_wrapper() -> models.Transformation:
        creation = seed._creation(ctx)
        return graph_logic._sequence(
            input_system=models.CoordinateSystem.objects.get(pk=intrinsic),
            output_system=models.CoordinateSystem.objects.get(pk=world),
            scale=[2.0, 2.0],
            translation=[0.5, 0.5],
            ctx=creation,
        )

    wrapper = await sync_to_async(build_wrapper)()
    result = await schema.execute(UPDATE_TRANSFORM, context_value=ctx, variable_values={"input": {"id": str(wrapper.pk), "scale": [1.0, 1.0]}})
    assert result.errors and "its parameters live on its children" in str(result.errors[0]), str(result.errors and result.errors[0])


@pytest.mark.django_db(transaction=True)
def test_the_logic_layer_holds_the_same_line_for_internal_callers(authenticated_context: HttpContext) -> None:
    """The writers below the API refuse what the union makes unrepresentable above it.

    The parse layer is the API's gate; these are the same checks in
    `build_registration_edge` / `write_relation_edge`, so an internal caller cannot
    reintroduce the silent drop the union removed.
    """
    ctx = seed._creation(authenticated_context)

    def system(name: str) -> models.CoordinateSystem:
        made = models.CoordinateSystem.objects.create(name=name, creator=ctx.user, organization=ctx.organization)
        graph_logic.create_pixel_axes(made, seed.YX_AXES)
        return made

    a, b = system("a"), system("b")

    with pytest.raises(ValueError, match="does not read `translation`"):
        graph_logic.build_registration_edge(input_system=a, output_system=b, kind="SCALE", scale=[1.0, 1.0], translation=[1.0, 1.0], ctx=ctx)
    with pytest.raises(ValueError, match="takes no `inputAxes`"):
        graph_logic.build_registration_edge(input_system=a, output_system=b, kind="SCALE", scale=[1.0, 1.0], input_axes=["y", "x"], ctx=ctx)
    with pytest.raises(ValueError, match="belongs to an UNMAPPABLE edge"):
        graph_logic.build_registration_edge(input_system=a, output_system=b, kind="SCALE", scale=[1.0, 1.0], reason="because", ctx=ctx)
    with pytest.raises(ValueError, match="cannot be created directly"):
        graph_logic.build_registration_edge(input_system=a, output_system=b, kind="SEQUENCE", ctx=ctx)
    with pytest.raises(ValueError, match="does not read `affine`"):
        graph_logic.write_relation_edge(name="d", input_system=a, output_system=b, kind="IDENTITY", affine=[[1.0]], ctx=ctx)

    # The value rules hold here too: the union makes a collapsing map unrepresentable
    # through GraphQL, and nothing makes it unrepresentable to an internal writer.
    with pytest.raises(ValueError, match="no factor may be zero"):
        graph_logic.build_registration_edge(input_system=a, output_system=b, kind="SCALE", scale=[0.0, 1.0], ctx=ctx)
    with pytest.raises(ValueError, match="no row's linear part may be all zeros"):
        graph_logic.write_relation_edge(name="d", input_system=a, output_system=b, kind="AFFINE", affine=[[0.0, 0.0, 1.0], [0.0, 1.0, 0.0]], ctx=ctx)

    # The one deliberate loosening: a BY_DIMENSION derivation's optional parameters now
    # persist, exactly as the registration path always stored them.
    edge = graph_logic.write_relation_edge(
        name="projection",
        input_system=a,
        output_system=b,
        kind="BY_DIMENSION",
        input_axes=["y", "x"],
        output_axes=["y", "x"],
        scale=[2.0, 2.0],
        ctx=ctx,
    )
    assert edge.params == {"scale": [2.0, 2.0]}


def test_a_derivation_may_state_any_creatable_kind() -> None:
    """The derivation subset is gone: one union, and MAP_AXIS/FIELD parse like any member.

    This is the parse every ``TransformInput.to_pydantic`` runs -- derivations included,
    since ``DerivationInput``/``DerivedFromInput`` carry the same union now.
    """
    member = parse_union_member(TRANSFORM_MEMBERS, {"kind": "MAP_AXIS", "input_axes": ["x", "y"], "output_axes": ["y", "x"]}, noun="transformation")
    assert isinstance(member, MapAxisTransformInputModel)

    member = parse_union_member(TRANSFORM_MEMBERS, {"kind": "FIELD", "field": "1", "input_axes": ["y", "x"], "output_axes": ["i"]}, noun="transformation")
    assert isinstance(member, FieldTransformInputModel)


def test_the_union_is_published_for_codegen() -> None:
    """The SDL carries the members, their annotations, and the flat unions they describe.

    The member inputs are referenced by no field -- dropping them from `types=[...]`
    would silently erase them from the SDL, so their presence is pinned here, exactly
    like the polymorphic read-side subtypes.
    """
    sdl = schema.as_str()
    assert "directive @unionElementOf(union: String!, discriminator: String!, key: String!) repeatable on INPUT_OBJECT" in sdl
    for member in [
        # IDENTITY included: the discriminator is a field, so the input is not empty,
        # and a client that cannot build this member can only say "same grid" by
        # omitting the transform -- which this schema reads as UNMAPPABLE, the opposite.
        "IdentityTransformInput",
        "ScaleTransformInput",
        "TranslationTransformInput",
        "AffineTransformInput",
        "RotationTransformInput",
        "ByDimensionTransformInput",
        "UnmappableTransformInput",
        "MapAxisTransformInput",
        "FieldTransformInput",
    ]:
        start = sdl.find(f"input {member} ")
        assert start >= 0, f"{member} missing from the SDL"
        header = sdl[start : sdl.find("{", start)]
        assert '@unionElementOf(union: "TransformInput", discriminator: "kind", key: ' in header, f"{member} lacks its annotation"

        # A member declares the parent's common fields as well as its own -- for this union
        # that is `kind` alone, and it defaults to the member's own key. GraphQL input types
        # have no inheritance, so a member that omits it generates a type a client cannot
        # construct without threading the discriminator in by hand.
        body = sdl[start : sdl.find("\n}", start)]
        key = header[header.find('key: "') + 6 : header.rfind('"')]
        assert f"kind: CreatableTransformKind! = {key}" in body, f"{member} does not declare `kind` defaulting to {key}"

    assert "RelationInput" not in sdl, "the derivation subset is gone: one union input, everywhere"
    assert "transform: TransformInput!" in sdl, "createTransformation requires its transform"
    assert "transform: TransformInput" in sdl
    creatable = sdl[sdl.find("enum CreatableTransformKind") : sdl.find("}", sdl.find("enum CreatableTransformKind"))]
    assert "SEQUENCE" not in creatable and "BIJECTION" not in creatable, "wrapper kinds stay out of the creatable enum"
