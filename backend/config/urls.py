from django.urls import path

from routing_app import views

urlpatterns = [
    path("api/health", views.health_view, name="health"),
    path("api/geocode", views.geocode_view, name="geocode"),
    path("api/trips", views.trips_view, name="trips"),
    path("", views.spa_index_view, name="spa_index"),
]
