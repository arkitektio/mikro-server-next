from django.contrib import admin

# Register your models here.
from core.models import Image, Instrument, Dataset
from simple_history.admin import SimpleHistoryAdmin


class DatasetHistoryAdmin(SimpleHistoryAdmin):
    list_display = ["id", "name"]
    history_list_display = ["name"]
    search_fields = ["name", "user__username"]


admin.site.register(Image)
admin.site.register(Instrument)
admin.site.register(Dataset, DatasetHistoryAdmin)
