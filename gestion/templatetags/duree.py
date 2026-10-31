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
