"""
URL configuration for mikro_server project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from strawberry_django.views import AsyncGraphQLView
from kante.path import dynamicpath
from mikro_server.schema import schema
from django.http import HttpResponse
from health_check.views import MainView
from django.views.decorators.csrf import csrf_exempt

def fakts_challenge(request):
    """
    Placeholder view for the .well-known/fakts-challenge endpoint.
    This should be replaced with the actual logic to handle the challenge.
    """
    return HttpResponse("Fakts Challenge Endpoint", status=200)



urlpatterns = [
    dynamicpath("admin/", admin.site.urls),
    dynamicpath("ht",  csrf_exempt(MainView.as_view()), name="health_check"),
    dynamicpath(".well-known/fakts-challenge", fakts_challenge, name="fakts-challenge"),
]
