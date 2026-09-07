from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import (
    AddressViewSet,
    GoogleLoginView,
    LoginView,
    LogoutView,
    ProfileView,
    RegisterView,
    ResetPasswordView,
    SendOTPView,
    VerifyOTPView,
)

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("login/otp/send/", SendOTPView.as_view(), name="send-otp"),
    path("login/otp/verify/", VerifyOTPView.as_view(), name="verify-otp"),
    path("login/google/", GoogleLoginView.as_view(), name="google-login"),
    path("password/reset/", ResetPasswordView.as_view(), name="reset-password"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("", include(router.urls)),
]
