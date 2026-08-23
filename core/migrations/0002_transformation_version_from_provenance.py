"""Drop ``Transformation.version``; the number is now counted from the edge's provenance.

The column was a second record of a fact ``provenance`` already kept. Every save writes a
history row, so "has this edge been rewritten" was answerable without a counter -- and the
counter was the weaker answer of the two, because keeping it was every writer's job and only
``updateTransformation`` ever did it. Any other write left a chain that had moved reading as
though it had not.

Nothing is lost on the read side. ``Transformation.version`` is still a GraphQL field, so the
``(id, version)`` cache key clients are given in ``docs/attribute-plans-api.md`` still works;
it now counts history rows, which is why a freshly created edge still reads 1. The stored
numbers on existing annotations (``created_with_transforms``) are not migrated: they are
provenance about what the chain read when a shape was drawn, they are compared for equality
only, and re-deriving them against the new counting would be inventing a past reading. A shape
authored before this migration therefore reads stale once, recomputes its box, and is correct
from then on -- the safe direction to be wrong in.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicaltransformation",
            name="version",
        ),
        migrations.RemoveField(
            model_name="transformation",
            name="version",
        ),
    ]
