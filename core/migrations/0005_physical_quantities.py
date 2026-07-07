# Migrate physical-quantity columns from fixed-unit floats to kanne_server
# QuantityField (an integer count of a canonical sub-unit).
#
# The Django-generated AlterField would emit ``... TYPE bigint USING col::bigint``,
# which truncates the fractional part *before* any rescale (0.325 µm -> 0). Instead
# each column is rescaled in-place with an exact ``numeric`` USING clause, so no
# precision is lost:
#   pixel size  micrometer -> picometer : x 1e6
#   wavelength  nanometer  -> picometer : x 1e3
#   timepoint   millisecond-> picosecond: x 1e9  (also renamed ms_since_start -> time_since_start)
#
# Project state is left identical to what makemigrations produced (so historical
# model state stays correct); only the database DDL is overridden via
# SeparateDatabaseAndState.

import kanne_server.fields
from django.db import migrations


def _rescale(table, column, factor):
    """A data-preserving float->bigint type change that multiplies by ``factor``."""
    return migrations.RunSQL(
        sql=[
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE bigint '
            f'USING round("{column}"::numeric * {factor})::bigint'
        ],
        reverse_sql=[
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE double precision '
            f'USING ("{column}"::numeric / {factor})::double precision'
        ],
    )


def _rename_and_rescale(table, old, new, factor):
    """Rename ``old`` -> ``new`` and rescale float->bigint by ``factor`` (reversible)."""
    return migrations.RunSQL(
        sql=[
            f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}"',
            f'ALTER TABLE "{table}" ALTER COLUMN "{new}" TYPE bigint '
            f'USING round("{new}"::numeric * {factor})::bigint',
        ],
        reverse_sql=[
            f'ALTER TABLE "{table}" ALTER COLUMN "{new}" TYPE double precision '
            f'USING ("{new}"::numeric / {factor})::double precision',
            f'ALTER TABLE "{table}" RENAME COLUMN "{new}" TO "{old}"',
        ],
    )


def _quantity_field(base_unit, help_text):
    """A nullable QuantityField mirroring the model definitions (for project state)."""
    return kanne_server.fields.QuantityField(
        base_unit=base_unit, blank=True, null=True, help_text=help_text
    )


def _type_change(model_name, table, field_name, help_text, factor):
    """A type-change (no rename) as SeparateDatabaseAndState."""
    return migrations.SeparateDatabaseAndState(
        state_operations=[
            migrations.AlterField(
                model_name=model_name,
                name=field_name,
                field=_quantity_field('picometer', help_text),
            ),
        ],
        database_operations=[_rescale(table, field_name, factor)],
    )


def _timepoint_change(model_name, table):
    """Rename ms_since_start -> time_since_start and rescale ms->ps, preserving data."""
    return migrations.SeparateDatabaseAndState(
        state_operations=[
            migrations.RemoveField(model_name=model_name, name='ms_since_start'),
            migrations.AddField(
                model_name=model_name,
                name='time_since_start',
                field=_quantity_field(
                    'picosecond', 'The time since the start of the era, stored in picoseconds'
                ),
            ),
        ],
        database_operations=[
            _rename_and_rescale(table, 'ms_since_start', 'time_since_start', 1_000_000_000),
        ],
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_remove_historicallayer_clim_max_and_more'),
    ]

    operations = [
        _timepoint_change('timepointview', 'core_timepointview'),
        _timepoint_change('historicaltimepointview', 'core_historicaltimepointview'),
        _type_change('camera', 'core_camera', 'pixel_size_x', 'The physical pixel size in x direction, stored in picometers', 1_000_000),
        _type_change('camera', 'core_camera', 'pixel_size_y', 'The physical pixel size in y direction, stored in picometers', 1_000_000),
        _type_change('historicalcamera', 'core_historicalcamera', 'pixel_size_x', 'The physical pixel size in x direction, stored in picometers', 1_000_000),
        _type_change('historicalcamera', 'core_historicalcamera', 'pixel_size_y', 'The physical pixel size in y direction, stored in picometers', 1_000_000),
        _type_change('channelview', 'core_channelview', 'emission_wavelength', 'The emission wavelength of the fluorophore, stored in picometers', 1_000),
        _type_change('channelview', 'core_channelview', 'excitation_wavelength', 'The excitation wavelength of the fluorophore, stored in picometers', 1_000),
        _type_change('historicalchannelview', 'core_historicalchannelview', 'emission_wavelength', 'The emission wavelength of the fluorophore, stored in picometers', 1_000),
        _type_change('historicalchannelview', 'core_historicalchannelview', 'excitation_wavelength', 'The excitation wavelength of the fluorophore, stored in picometers', 1_000),
    ]
