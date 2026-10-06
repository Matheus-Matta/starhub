from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.notificacoes.models import Notificacao


@staff_member_required
@require_POST
def marcar_lidas(request):
    """Todas as do usuario como lidas e volta para a pagina em que ele estava."""
    Notificacao.all_objects.filter(usuario=request.user, lida=False).update(lida=True)
    volta = request.META.get("HTTP_REFERER", "")
    seguro = url_has_allowed_host_and_scheme(volta, {request.get_host()},
                                             require_https=request.is_secure())
    return HttpResponseRedirect(volta if seguro else "/admin/")
