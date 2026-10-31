from django.conf import settings


def atelier(request):
    u = request.user
    return {
        "ATELIER_NOM": settings.ATELIER_NOM,
        "est_admin": u.is_authenticated and u.is_active and u.is_superuser,
    }
