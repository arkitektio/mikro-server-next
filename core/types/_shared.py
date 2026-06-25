def build_prescoped_queryset(info, queryset):
    if (info.variable_values.get("filters") or {}).get("scope") is None:
        queryset = queryset.filter(organization=info.context.request.organization)

    return queryset
