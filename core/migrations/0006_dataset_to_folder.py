"""Rename ``Dataset`` to ``Folder``.

Three renames of one fact, in one migration so a database is never half-renamed: the
model (and its ``Historical`` twin), the ``dataset`` FK on everything that pointed at it,
and the ``auth_permission`` codenames that guardian's object-level grants hang off.

Hand-written rather than autodetected. ``makemigrations`` asks "did you rename dataset to
folder?" interactively, and a RenameModel plus a dozen RenameFields in one autodetector
pass is exactly where it degrades into drop-and-recreate -- which for a rename would throw
away every row. The shape follows ``0019_axis_naming``.

Three things are renamed implicitly and need no operation of their own: the tables
``core_dataset`` / ``core_historicaldataset`` (derived from the class name, no ``db_table``
is set), the M2M table ``core_dataset_pinned_by``, and the ``django_content_type`` row --
the contenttypes app injects a ``RenameContentType`` after every ``RenameModel`` it sees,
so the row is updated in place and guardian's ``UserObjectPermission.content_type_id``
survives untouched.

``Render`` is abstract, which is why ``blurhash``, ``video`` and ``snapshot`` each need
their own ``RenameField``: one line in ``core/models/image.py`` is three tables.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


# (concrete model, its simple_history twin) for every model holding a `dataset` FK that
# pointed at the old `Dataset`. `filelink.dataset` is deliberately absent -- it points at
# `ADataset`, and renaming it would break four UniqueConstraints and mean the wrong thing.
_FK_HOLDERS = [
    ("image", "historicalimage"),
    ("file", "historicalfile"),
    ("table", "historicaltable"),
    ("blurhash", "historicalblurhash"),
    ("video", "historicalvideo"),
    ("snapshot", "historicalsnapshot"),
]

# Django's default permissions for a model, and the verbose name each one reads.
_PERMS = [("add", "Can add"), ("change", "Can change"), ("delete", "Can delete"), ("view", "Can view")]


def _content_type(apps):
    """The renamed content-type row, tolerating either spelling.

    `RenameContentType` is injected right after the `RenameModel` above, so by the time
    this runs the row should say `folder` -- but this migration must also apply cleanly on
    a database where contenttypes is unmigrated or the injection did not fire.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    return ContentType.objects.filter(app_label="core", model__in=("folder", "dataset")).first()


def rename_permissions(apps, schema_editor):
    """Point the existing `*_dataset` permissions at the new name.

    Without this, post_migrate's `create_permissions` *adds* four `*_folder` rows next to
    the four stale `*_dataset` ones. Existing guardian grants FK the old rows, so
    `assign_perm("view_folder", ...)` would write against a different row than the grants
    users already hold and object-level permissions would silently stop matching.
    """
    Permission = apps.get_model("auth", "Permission")
    ct = _content_type(apps)
    if ct is None:
        return
    for action, verbose in _PERMS:
        Permission.objects.filter(content_type=ct, codename=f"{action}_dataset").update(
            codename=f"{action}_folder",
            name=f"{verbose} folder",
        )


def unrename_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ct = _content_type(apps)
    if ct is None:
        return
    for action, verbose in _PERMS:
        Permission.objects.filter(content_type=ct, codename=f"{action}_folder").update(
            codename=f"{action}_dataset",
            name=f"{verbose} dataset",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_annotation_bbox_help_text"),
        ("authentikate", "0006_alter_app_identifier_alter_release_unique_together"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Dropped first, while the model is still called `dataset`, and rebuilt under the
        # new name at the end. The constraint name itself carries the old vocabulary.
        migrations.RemoveConstraint(
            model_name="dataset",
            name="only_one_dataset_per_parent_and_name",
        ),
        migrations.RenameModel(old_name="Dataset", new_name="Folder"),
        migrations.RenameModel(old_name="HistoricalDataset", new_name="HistoricalFolder"),
        migrations.AlterModelOptions(
            name="historicalfolder",
            options={
                "get_latest_by": ("history_date", "history_id"),
                "ordering": ("-history_date", "-history_id"),
                "verbose_name": "historical folder",
                "verbose_name_plural": "historical folders",
            },
        ),
        # The FK column on every holder, concrete and historical. The historical half is
        # the one that hides: `0020_historical_tables_catch_up` exists because this pairing
        # was missed once already.
        *[
            migrations.RenameField(model_name=model, old_name="dataset", new_name="folder")
            for concrete, historical in _FK_HOLDERS
            for model in (concrete, historical)
        ],
        migrations.AddConstraint(
            model_name="folder",
            constraint=models.UniqueConstraint(
                fields=("parent", "name"),
                name="only_one_folder_per_parent_and_name",
            ),
        ),
        # Re-apply the reworded `help_text` and the renamed reverse accessors
        # (`created_datasets` -> `created_folders`, `datasets` -> `folders`,
        # `pinned_datasets` -> `pinned_folders`). All no-ops in SQL bar the M2M, but the
        # migration state has to match the models or every later `makemigrations` reopens
        # them.
        migrations.AlterField(
            model_name="folder",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, help_text="The time the folder was created"),
        ),
        migrations.AlterField(
            model_name="folder",
            name="creator",
            field=models.ForeignKey(help_text="The user that created the folder", on_delete=django.db.models.deletion.CASCADE, related_name="created_folders", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="folder",
            name="description",
            field=models.CharField(blank=True, help_text="The description of the folder", max_length=1000, null=True),
        ),
        migrations.AlterField(
            model_name="folder",
            name="description_two",
            field=models.CharField(blank=True, help_text="The description of the folder, this is a second description field", max_length=1000, null=True),
        ),
        migrations.AlterField(
            model_name="folder",
            name="is_default",
            field=models.BooleanField(default=False, help_text="Whether the folder is the current default folder for the user"),
        ),
        migrations.AlterField(
            model_name="folder",
            name="membership",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="folders", to="authentikate.membership"),
        ),
        migrations.AlterField(
            model_name="folder",
            name="name",
            field=models.CharField(help_text="The name of the folder", max_length=200),
        ),
        migrations.AlterField(
            model_name="folder",
            name="pinned_by",
            field=models.ManyToManyField(blank=True, help_text="The users that have pinned the folder", related_name="pinned_folders", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="historicalfolder",
            name="created_at",
            field=models.DateTimeField(blank=True, editable=False, help_text="The time the folder was created"),
        ),
        migrations.AlterField(
            model_name="historicalfolder",
            name="creator",
            field=models.ForeignKey(blank=True, db_constraint=False, help_text="The user that created the folder", null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name="+", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="historicalfolder",
            name="description",
            field=models.CharField(blank=True, help_text="The description of the folder", max_length=1000, null=True),
        ),
        migrations.AlterField(
            model_name="historicalfolder",
            name="description_two",
            field=models.CharField(blank=True, help_text="The description of the folder, this is a second description field", max_length=1000, null=True),
        ),
        migrations.AlterField(
            model_name="historicalfolder",
            name="is_default",
            field=models.BooleanField(default=False, help_text="Whether the folder is the current default folder for the user"),
        ),
        migrations.AlterField(
            model_name="historicalfolder",
            name="name",
            field=models.CharField(help_text="The name of the folder", max_length=200),
        ),
        migrations.RunPython(rename_permissions, unrename_permissions),
    ]
