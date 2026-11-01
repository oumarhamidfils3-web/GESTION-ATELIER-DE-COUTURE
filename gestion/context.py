from django.conf import settings


def atelier(request):
    u = request.user
    return {
        "ATELIER_NOM": settings.ATELIER_NOM,
        "ATELIER_SOUS_TITRE": settings.ATELIER_SOUS_TITRE,
        "est_admin": u.is_authenticated and u.is_active and u.is_superuser,
        "membre_connecte": (not u.is_authenticated) and bool(request.session.get("membre_id")),
    }
