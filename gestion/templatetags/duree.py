from django import template

register = template.Library()


@register.filter
def duree(sec):
    try:
        sec = max(int(sec), 0)
    except (TypeError, ValueError):
        return "—"
    h, r = divmod(sec, 3600)
    return f"{h} h {r // 60:02d} min"


@register.filter
def initiales(nom):
    mots = [m for m in (nom or "").split() if m]
    if not mots:
        return "?"
    return (mots[0][0] + (mots[-1][0] if len(mots) > 1 else "")).upper()
