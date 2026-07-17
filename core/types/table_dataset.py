"""GraphQL types for the parquet-backed table dataset and its declared columns."""

from typing import List, Optional

from strawberry import auto

import kante
from kante.types import Info

from datalayer.types import ParquetStore

from core import enums, filters, models, order, scalars
from core.logic import graph as graph_logic
from core.types.auth import ProvenanceEntry, Task, User
from core.types.coords import CoordinateSystem, Transformation


@kante.django_type(
    models.TableColumn,
    description="One declared column of a table dataset: its name, dtype and role. A COORDINATE column is also an axis of the table's space",
)
class TableDatasetColumn:
    """One declared column of a table dataset."""

    id: auto
    order: int
    name: str
    dtype: str
    role: enums.TableColumnRole
    axis_type: enums.AxisType | None
    unit: str | None
    long_name: str | None
    description: str | None
    references: Optional["TableDataset"] = kante.django_field(
        description="The table whose rows this column's values identify -- a declared foreign key, e.g. an `instance_id` column referencing a table of tracks. The target is keyed by its single INDEX coordinate column; look a value up there. Null for a column that identifies nothing"
    )


@kante.django_type(
    models.TableDataset,
    filters=filters.TableDatasetFilter,
    ordering=order.TableDatasetOrder,
    pagination=True,
    description="A parquet-backed table whose rows are scientific records (segmented objects, localizations, cells). It owns a coordinate system whose axes are its coordinate columns, which is what makes a localization table placeable; a table with no coordinate columns enumerates its rows and its lineage edge is UNMAPPABLE. Its store, its columns and that coordinate system are fixed at creation -- only `name` and `description` can be updated, and a recomputation is a new table rather than an edit of this one. Read the rows directly from the Parquet store with a datalayer access grant rather than paginating through GraphQL",
)
class TableDataset:
    """A parquet-backed table dataset."""

    id: auto
    name: auto
    description: str | None
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(
        description="Every change made to this table: who created it, and every subsequent rename or redescription, attributed to the client, user and task it happened under. Only `name` and `description` can change -- the store, the columns and the coordinate system derived from them are fixed at creation"
    )
    store: ParquetStore = kante.django_field(description="The Parquet store holding the rows. Request an access grant from it and read the Parquet directly")
    columns: List[TableDatasetColumn] = kante.django_field(description="The declared column schema, in order. The COORDINATE columns are the axes of this table's coordinate system")
    coordinate_system: CoordinateSystem = kante.django_field(description="The coordinate system this table owns. Its axes are the table's coordinate columns (or a single INDEX axis for a pure measurement table)")
    created_through: Task | None = kante.django_field(description="The task this table was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")
    referenced_by: List[TableDatasetColumn] = kante.django_field(
        description="Every column, in any table, that declares this table as its reference target -- the reverse of `TableDatasetColumn.references`. This table cannot be deleted while any of them exist"
    )

    @kante.django_field(
        description="The edge from this table's space back into the data it was computed from. UNMAPPABLE for a measurement table (its rows are not positions), a real map for a placeable localization table. Null for a freestanding table. It is the same relation a derived dataset's `derivedFrom` records"
    )
    def derived_from(self, info: Info) -> Transformation | None:
        """The edge relating this table's space to the data it came from."""
        system = getattr(self, "coordinate_system", None)
        return graph_logic.collection_derivation_edge(system) if system else None

    @kante.django_field(description="The table's axis names, in order. Derived from the coordinate columns")
    def axis_names(self, info: Info) -> List[str]:
        """The table's axis names."""
        return self.axis_names

    @kante.django_field(description="How this table was produced: the run, its parameters and its inputs")
    def provenance_metadata(self, info: Info) -> scalars.Any:
        """How this table was produced."""
        return self.provenance_metadata
