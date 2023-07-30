from django.contrib import admin
from authentikate.models import App, User

# Register your models here.

admin.site.register(User)
admin.site.register(App)
