from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission


class AccessProfileBackend(ModelBackend):
    """Permissoes de grupo vem somente do perfil controlado pelo sistema."""

    def get_group_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()
        cache = getattr(user_obj, "_access_profile_perm_cache", None)
        if cache is None:
            profile_id = getattr(user_obj, "access_profile_id", None)
            permissions = Permission.objects.none()
            if profile_id:
                permissions = Permission.objects.filter(group__access_profiles__id=profile_id)
            cache = {
                f"{app_label}.{codename}"
                for app_label, codename in permissions.values_list(
                    "content_type__app_label", "codename"
                ).order_by()
            }
            user_obj._access_profile_perm_cache = cache
        return cache
