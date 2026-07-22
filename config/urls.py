from django.contrib import admin
from django.urls import include, path

from api.v1 import api_v1
from core import views

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("healthz", views.healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("api/v1/", api_v1.urls),
]
