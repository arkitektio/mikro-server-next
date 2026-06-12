"""Add the organization FK to the previously unscoped models.

The fields are added nullable, backfilled, then made non-nullable so the
migration also works on databases with existing rows. The backfill derives
the organization where a direct relation exists (Era via its instrument)
and otherwise assigns the first organization — fine for single-org
deployments; multi-org deployments with pre-existing rows should review the
assignment afterwards.
"""

import django.db.models.deletion
from django.db import migrations, models

SCOPED_MODELS = ["Era", "Experiment", "MultiWellPlate", "RenderTree", "ROIGroup", "Scene", "ViewCollection"]

# simple_history shadow models (RenderTree has no ProvenanceField); their FKs
# are nullable by design, so they need no backfill.
HISTORICAL_MODELS = ["historicalera", "historicalexperiment", "historicalmultiwellplate", "historicalroigroup", "historicalscene", "historicalviewcollection"]


def backfill_organizations(apps, schema_editor):
    """Assign an organization to every pre-existing row."""
    Organization = apps.get_model("authentikate", "Organization")
    default_org = Organization.objects.order_by("pk").first()

    Era = apps.get_model("core", "Era")
    for era in Era.objects.filter(organization__isnull=True).select_related("instrument"):
        era.organization = era.instrument.organization if era.instrument else default_org
        if era.organization is None:
            raise RuntimeError("Cannot backfill core.Era: no organization exists")
        era.save(update_fields=["organization"])

    for model_name in SCOPED_MODELS:
        if model_name == "Era":
            continue
        model = apps.get_model("core", model_name)
        if model.objects.filter(organization__isnull=True).exists():
            if default_org is None:
                raise RuntimeError(f"Cannot backfill core.{model_name}: no organization exists")
            model.objects.filter(organization__isnull=True).update(organization=default_org)


class Migration(migrations.Migration):
    dependencies = [
        ("authentikate", "0005_alter_client_client_id"),
        ("core", "0005_alter_channellabel_anchor_alter_lightpath_anchor"),
    ]

    operations = (
        [
            migrations.AddField(
                model_name=model_name.lower(),
                name="organization",
                field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to="authentikate.organization"),
            )
            for model_name in SCOPED_MODELS
        ]
        + [migrations.RunPython(backfill_organizations, migrations.RunPython.noop)]
        + [
            migrations.AlterField(
                model_name=model_name.lower(),
                name="organization",
                field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="authentikate.organization"),
            )
            for model_name in SCOPED_MODELS
        ]
        + [
            migrations.AddField(
                model_name=model_name,
                name="organization",
                field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name="+", to="authentikate.organization"),
            )
            for model_name in HISTORICAL_MODELS
        ]
    )
