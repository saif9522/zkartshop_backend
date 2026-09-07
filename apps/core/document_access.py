"""
Signed document access — KYC documents (Aadhaar, PAN, GST certs, bank proof,
etc.) must not be reachable by anyone who merely has the URL, per the
"restrict document access based on user roles" security requirement.

Instead of exposing the raw MEDIA URL, serializers call
`signed_document_url(request, instance, field_name)`, which embeds a signed,
5-minute-lived token identifying (app_label.model, pk, field, requesting
user). `ServeDocumentView` verifies the signature, checks it hasn't expired,
and re-checks the requesting user still has permission (owner or the right
admin permission) before streaming the file — so a leaked link stops working
in minutes and never worked for anyone but the intended viewer to begin with.
"""
from django.apps import apps
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

SIGNER = signing.TimestampSigner(salt="kyc-document-access")
MAX_AGE_SECONDS = 300  # 5 minutes — long enough to load a page, short enough a leaked link isn't a standing hole


def signed_document_url(request, instance, field_name):
    """Returns a signed, short-lived URL for one document field, or None if that field is empty."""
    file_field = getattr(instance, field_name)
    if not file_field:
        return None

    app_label = instance._meta.app_label
    model_name = instance._meta.model_name
    payload = f"{app_label}.{model_name}:{instance.pk}:{field_name}:{request.user.id}"
    token = SIGNER.sign(payload)
    return request.build_absolute_uri(f"/api/v1/documents/serve/?token={token}")


def _check_permission(requesting_user, instance, field_name):
    """Owner of the record, or an admin with the matching manage-permission, may view it."""
    from apps.accounts.models import Role
    from apps.delivery.models import DeliveryProfile
    from apps.superadmin.permissions import CanManageDeliveryPartners, CanManageVendors
    from apps.vendors.models import Vendor

    fake_request = type("FakeRequest", (), {"user": requesting_user})()

    if isinstance(instance, Vendor):
        if instance.owner_id == requesting_user.id:
            return True
        if requesting_user.role in (Role.ADMIN, Role.SUPER_ADMIN):
            return CanManageVendors().has_permission(fake_request, None)
        return False

    if isinstance(instance, DeliveryProfile):
        if instance.user_id == requesting_user.id:
            return True
        if requesting_user.role in (Role.ADMIN, Role.SUPER_ADMIN):
            return CanManageDeliveryPartners().has_permission(fake_request, None)
        return False

    return False


class ServeDocumentView(APIView):
    """Verifies the signed token and streams the file — the only way a KYC document is ever actually served."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = request.query_params.get("token", "")
        try:
            payload = SIGNER.unsign(token, max_age=MAX_AGE_SECONDS)
        except signing.SignatureExpired:
            raise PermissionDenied("This document link has expired — reopen the page to get a fresh one.")
        except signing.BadSignature:
            raise PermissionDenied("Invalid document link.")

        try:
            model_ref, pk, field_name, issued_for_user_id = payload.split(":")
            app_label, model_name = model_ref.split(".")
        except ValueError:
            raise PermissionDenied("Invalid document link.")

        # The link was signed for a specific viewer — even if forwarded, it won't work for anyone else.
        if str(request.user.id) != issued_for_user_id:
            raise PermissionDenied("This document link isn't valid for your account.")

        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            raise Http404("Document not found.")

        try:
            instance = model.objects.get(pk=pk)
        except model.DoesNotExist:
            raise Http404("Document not found.")

        if not _check_permission(request.user, instance, field_name):
            raise PermissionDenied("You don't have permission to view this document.")

        file_field = getattr(instance, field_name, None)
        if not file_field:
            raise Http404("Document not found.")

        return FileResponse(file_field.open("rb"), filename=file_field.name.split("/")[-1])


class SignedDocumentFieldsMixin:
    """
    Mix into any ModelSerializer that exposes file/image fields containing
    sensitive KYC documents. List the field names in `document_field_names`
    and their raw (permanently-public) MEDIA URLs get swapped for signed,
    5-minute-lived ones in the response — the serializer still declares them
    normally in Meta.fields, this just overrides what actually goes out.
    """

    document_field_names: list = []

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None:
            for name in self.document_field_names:
                if name in data:
                    data[name] = signed_document_url(request, instance, name)
        return data
