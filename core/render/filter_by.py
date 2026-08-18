"""Filtering objects by a column of the table their source keys into.

The sibling of :mod:`core.render.color_by`, over the same relation and answered from the same
place: a collection's objects carry ids, a ``FIELD`` edge keys them to a table of per-object
rows, and a column of that table decides -- here whether an object is *drawn* rather than what
colour it takes. So the two share their boundary check (the table must be reachable, the column
must exist) and differ only in what they do with the value.

**Which rule shape applies follows from the column's declared role**, exactly as it does for
``colorBy``'s colormap-vs-classColors: a measure column (COORDINATE, ATTRIBUTE) has an order, so
it is bounded with ``min``/``max``; a categorical one (ID, LABEL, TRACK_ID, COLOR) has none, so
it is matched against an explicit set of ``values``. Naming both is refused at the boundary --
the table already settled which of the two a column is, and a second answer here could only
disagree with it.

The bounds are bare numbers, deliberately, and they are in the column's own declared ``unit``
(``TableColumn.unit``). A quantity here would be a second statement of a unit the table already
carries, free to drift from it; the column is the one place that says what "500" means.

Nothing here is a spatial fact and nothing here is executed server-side: a filter says which
objects a viewer draws, and the viewer runs it against the parquet it already reads. The server
stores the rule and refuses one nothing could run.
"""

from pydantic import BaseModel, Field, model_validator

from core.render.joins import JoinStepModel


class FilterByModel(BaseModel):
    """Draw only the objects whose row in the keyed table satisfies this rule.

    ``exclude`` inverts the whole rule rather than belonging to one half of it: "everything but
    the debris class" and "everything but the smallest objects" are the same operation over two
    different matches, and giving each half its own negation would be two ways to say one thing.
    """

    table: str
    column: str
    # The same chain :class:`~core.render.color_by.ColorByModel` carries, for the same reason and
    # checked by the same walker: a rule over a column two tables away is as legitimate as a
    # colouring by one. Empty is the direct case. See :mod:`core.render.joins`.
    join_path: list[JoinStepModel] = Field(default_factory=list)

    # The measure half: a closed, half-open or (with one bound) open interval, inclusive on both
    # ends. Two optional bounds rather than an operator and a value, because a range is the shape
    # the question actually has -- "volume between 100 and 500" is one rule, and expressing it as
    # two predicates that must both hold invites a picker entry that is half a rule.
    min: float | None = None
    max: float | None = None

    # The categorical half: the values that match, as strings. Strings even for integer ids,
    # matching `ColorByModel.class_colors`, whose keys are the same values under the same
    # constraint -- JSON object keys are strings, and one vocabulary for both beats two.
    values: list[str] | None = None

    exclude: bool = False

    @model_validator(mode="after")
    def _one_kind_of_rule(self) -> "FilterByModel":
        bounded = self.min is not None or self.max is not None
        if bounded and self.values is not None:
            raise ValueError(
                "`filterBy` takes either bounds (`min`/`max`, for a measure column) or `values` (for a categorical one), never both: which applies follows from the column's declared role, not from a choice here"
            )
        if not bounded and self.values is None:
            raise ValueError("A `filterBy` naming neither a bound nor any values matches every row, which is not a filter -- give it a `min`, a `max`, or a `values` list")
        return self

    @model_validator(mode="after")
    def _bounds_are_a_range(self) -> "FilterByModel":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"`min` is {self.min} and `max` is {self.max}, which is an empty range: nothing can be both above the one and below the other")
        return self

    @model_validator(mode="after")
    def _values_are_not_empty(self) -> "FilterByModel":
        # An empty list is not "match nothing" here, it is a caller who meant to send something.
        # "Draw nothing" is expressible -- switch the layer off -- and is never what a filter is for.
        if self.values is not None and not self.values:
            raise ValueError("`values` is empty, which would match no object at all. Omit the filter to draw everything, or hide the layer to draw nothing")
        return self


class MeshFilterByModel(FilterByModel):
    """One entry of a mesh layer's filter picker: a rule, and what to call it in the UI.

    A subclass for the same reason :class:`~core.render.color_by.MeshColorByModel` is one: the
    caption belongs to the picker, and only a mesh layer publishes one. Two entries over the
    same column are *allowed* here, unlike in the colour picker -- "small cells" and "large
    cells" are two different rules over one measure, and the label is what tells them apart.
    """

    label: str | None = None
