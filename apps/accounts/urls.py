from django.urls import path

from .views import login_view, logout_view, me, register, stats

urlpatterns = [
    path("register/", register, name="account-register"),
    path("login/", login_view, name="account-login"),
    path("logout/", logout_view, name="account-logout"),
    path("me/", me, name="account-me"),
    path("stats/", stats, name="account-stats"),
]
