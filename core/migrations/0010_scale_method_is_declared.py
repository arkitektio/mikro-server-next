"""A pyramid level says how it was downsampled, and a label pyramid may only say two things.

``ScaleInput.scale_method`` has existed since the initial schema, described as "recorded as
provenance on the level's transformation". It never was. The field sat on the strawberry
input and not on ``ScaleInputModel``, so ``to_pydantic()`` dropped it before any resolver
saw it -- every client that dutifully sent ``scaleMethod`` was sending it into nothing. This
migration is where it starts being stored.

It is stored on ``DataArray`` rather than on the level's transformation edge, because it is
a fact about how the *array* was computed, not about the map between the two spaces: the
edge says level 1's voxel grid is level 0's halved, which is equally true whether the
halving averaged or picked. The same reason ``shape`` lives here.

And it is a **stated** fact. Two arrays are all that survives a downsample and nothing in
the numbers says whether they were averaged or picked, so there is nothing to derive it
from -- which is exactly why the check it enables could not have existed before. Over an
array whose values are object ids, only NEAREST and MODE are honest: every other method
returns numbers that were not in the input, and an invented id is an object that does not
exist. ``createADataset`` now refuses a non-compliant pyramid on a dataset whose primary
derivation is declared CATEGORIZED.

**No backfill, and null does not mean compliant.** Existing levels were written by clients
whose ``scaleMethod`` went nowhere, so the honest value for every one of them is "not
recorded" -- guessing NEAREST would manufacture a reassurance nobody earned, and guessing
AREA would condemn pyramids that are fine. ``ADataset.pyramidIsLabelCompliant`` returns null
for exactly this state, distinct from both true and false.

``DataArray`` carries no ``Historical`` twin -- it never has -- so this is one AddField, not
the usual two.
"""

from django.db import migrations
import django_choices_field.fields

import core.enums


_HELP = (
    "How this level's voxels were computed from the level above it. Null for level 0, and for a level whose writer did not say. "
    "Over a dataset whose values are object ids only NEAREST and MODE are accepted -- everything else returns numbers that were not in the input, "
    "and an invented id is an object that does not exist"
)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_label_is_a_layer_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataarray",
            name="scale_method",
            field=django_choices_field.fields.TextChoicesField(
                blank=True,
                choices=[(choice.value, choice.label) for choice in core.enums.ScaleMethodChoices],
                choices_enum=core.enums.ScaleMethodChoices,
                max_length=8,
                null=True,
                help_text=_HELP,
            ),
        ),
    ]
