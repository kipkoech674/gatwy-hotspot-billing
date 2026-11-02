from django.contrib import admin
from django.urls import path
from hotspot import views

urlpatterns = [
    path("", views.portal, name="portal"),
    path("api/plans/", views.plans, name="plans"),
    path("api/checkout/", views.checkout, name="checkout"),
    path("api/purchases/<uuid:public_id>/", views.purchase_status, name="purchase-status"),
    path("api/reactivate/", views.reactivate, name="reactivate"),
    path("api/mpesa/callback/", views.mpesa_callback, name="mpesa-callback"),
    path("health/", views.health, name="health"),
    path("admin/", admin.site.urls),
]
