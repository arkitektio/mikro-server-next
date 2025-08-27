from django.contrib import admin

# Register your models here.
from core import models
from simple_history.admin import SimpleHistoryAdmin


class HistoryAdmin(SimpleHistoryAdmin):
    list_display = ["id"]
    history_list_display = ["name", "user"]
    search_fields = ["name", "user__username"]


admin.site.register(models.Image, HistoryAdmin)
admin.site.register(models.Instrument)
admin.site.register(models.Dataset, HistoryAdmin)
admin.site.register(models.Camera)
admin.site.register(models.ROI)
admin.site.register(models.Stage)
admin.site.register(models.ChannelView)
admin.site.register(models.Objective)
admin.site.register(models.Mesh)
admin.site.register(models.Era)
admin.site.register(models.MaskView)
admin.site.register(models.LabelAccessor)
admin.site.register(models.ImageAccessor)
admin.site.register(models.LabelView)
admin.site.register(models.AffineTransformationView)
admin.site.register(models.ZarrStore)
admin.site.register(models.S3Store)
admin.site.register(models.Snapshot)
admin.site.register(models.RenderTree)
