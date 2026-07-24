from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from api.v1 import api_v1
from core import views

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("site/<slug:page>.html", views.site_page, name="site_page"),
    path("report/", views.report_new, name="report_new"),
    path("report/import/", views.report_import, name="report_import"),
    path("report/media/", views.report_media_upload, name="report_media_upload"),
    path("issues/", views.issue_list, name="issue_list"),
    path("issues/<slug:public_id>/", views.issue_detail, name="issue_detail"),
    path("issues/<slug:public_id>/update/", views.update_new, name="update_new"),
    path("issues/<slug:public_id>/claim/", views.issue_claim, name="issue_claim"),
    path("issues/<slug:public_id>/flag/", views.issue_flag, name="issue_flag"),
    path("updates/<int:update_id>/flag/", views.update_flag, name="update_flag"),
    path("i/<slug:public_id>", views.issue_shortlink, name="issue_shortlink"),
    path("healthz", views.healthz, name="healthz"),
    path("manifest.webmanifest", views.webmanifest, name="webmanifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", api_v1.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
