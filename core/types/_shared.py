def build_prescoped_queryset(info, queryset):
    # Reads are always scoped to the request's organization; there is no
    # per-request scope override.
    return queryset.filter(organization=info.context.request.organization)
