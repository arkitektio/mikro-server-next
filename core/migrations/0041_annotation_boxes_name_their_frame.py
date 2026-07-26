"""An annotation collection names the frame its stored boxes are in.

`nearestAnnotations` and `AnnotationFilter.intersects` both say boxes only compare within
one frame -- and nothing in the schema *named* that frame, so two collections' boxes could
be compared with nothing to stop it, and a spatial query could recover it only by
re-walking `path_to_intrinsic`: a query per hop, and a second copy of a walk that can
disagree with the first.

**Null means the collection's own system**, which is why PROTECT here is safe. A real
self-FK under PROTECT would beat the collection's own CASCADE and make the collection
undeletable -- the trap `Transformation.field` documents and dodges the same way.

Nullable and unbackfilled. An existing collection's frame is exactly the thing this column
exists because the server cannot cheaply and reliably recompute, and a RunPython walking the
chain per collection would be that same fragile derivation, run once, frozen into a column.
Its meaning is right by default anyway: null reads as the collection's own space, which is
what a scene-minted collection's boxes are in.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0040_scene_units_are_similarity_scoped'),
    ]

    operations = [
        migrations.AddField(
            model_name='annotationcollection',
            name='bbox_system',
            field=models.ForeignKey(blank=True, help_text="The coordinate system this collection's stored bounding boxes are expressed in, when that is a system other than its own: the nearest intrinsic space its own system could reach at creation. Null when the boxes are in the collection's own space, which is the case whenever no chain resolves. Boxes only compare within one frame, and this names it. Written once at creation and immutable, because the stored boxes are numbers against it", null=True, on_delete=django.db.models.deletion.PROTECT, related_name='annotation_bbox_frames', to='core.coordinatesystem'),
        ),
        migrations.AddField(
            model_name='historicalannotationcollection',
            name='bbox_system',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text="The coordinate system this collection's stored bounding boxes are expressed in, when that is a system other than its own: the nearest intrinsic space its own system could reach at creation. Null when the boxes are in the collection's own space, which is the case whenever no chain resolves. Boxes only compare within one frame, and this names it. Written once at creation and immutable, because the stored boxes are numbers against it", null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.coordinatesystem'),
        ),
    ]
