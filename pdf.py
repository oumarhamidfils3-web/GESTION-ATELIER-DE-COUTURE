import io

import qrcode
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

INDIGO = colors.HexColor("#1f2a5a")
MADDER = colors.HexColor("#b3362f")
GRIS = colors.HexColor("#5b6070")


def url_membre(m):
    return settings.SITE_URL + reverse("scan", args=[m.token])


def url_renouvellement(m):
    return settings.SITE_URL + reverse("renouveler", args=[m.token])


def url_espace(m):
    return settings.SITE_URL + reverse("espace_membre", args=[m.token])


def _qr(url):
    img = qrcode.make(url, box_size=8, border=1)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return ImageReader(buf)


def _fit(c, text, font, size, maxw):
    while size > 6 and stringWidth(text, font, size) > maxw:
        size -= 0.5
    c.setFont(font, size)


def _photo(c, m, x, y, w, h):
    if m.photo:
        try:
            c.drawImage(m.photo.path, x, y, w, h, preserveAspectRatio=True, anchor="c", mask="auto")
            c.setStrokeColor(INDIGO)
            c.rect(x, y, w, h)
            return
        except Exception:
            pass
    c.setStrokeColor(GRIS)
    c.setDash(2, 2)
    c.rect(x, y, w, h)
    c.setDash()
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7)
    c.drawCentredString(x + w / 2, y + h / 2 - 2, "Photo")


def fiche_pdf(m):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    c.setFillColor(INDIGO)
    c.rect(0, H - 32 * mm, W, 32 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(20 * mm, H - 16 * mm, settings.ATELIER_NOM)
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, H - 24 * mm, "Fiche d'inscription")

    _photo(c, m, W - 20 * mm - 32 * mm, H - 80 * mm, 32 * mm, 40 * mm)

    y = H - 50 * mm
    lignes = [
        ("N° de membre", m.numero or ""),
        ("Nom complet", m.nom),
        ("Téléphone", m.telephone),
        ("Métier", m.metier or "—"),
        ("Adresse", m.adresse or "—"),
        ("Inscrit le", timezone.localtime(m.cree_le).strftime("%d/%m/%Y à %H:%M")),
        ("Enregistré par", (m.cree_par.get_full_name() or m.cree_par.username) if m.cree_par else "—"),
    ]
    for lib, val in lignes:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, y, lib)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(55 * mm, y, val)
        c.setStrokeColor(colors.HexColor("#d7d9e2"))
        c.line(20 * mm, y - 2.5 * mm, W - 20 * mm - 38 * mm, y - 2.5 * mm)
        y -= 9 * mm

    y -= 6 * mm
    c.setFillColor(INDIGO)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Forfait souscrit")
    y -= 7 * mm
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    recharges = list(m.recharges.all())
    if recharges:
        for r in recharges[:6]:
            h, rest = divmod(r.secondes, 3600)
            txt = (f"{timezone.localtime(r.cree_le).strftime('%d/%m/%Y')}  —  {r.forfait_nom}  —  "
                   f"{h} h {rest // 60:02d} min  —  {r.prix} FCFA")
            c.drawString(20 * mm, y, txt)
            y -= 6 * mm
    else:
        c.drawString(20 * mm, y, "Aucun forfait enregistré.")
        y -= 6 * mm

    y -= 6 * mm
    c.setFillColor(INDIGO)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Règles de l'atelier")
    y -= 7 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    for r in [
        "Présentez votre carte de membre au responsable à chaque entrée et à chaque sortie.",
        "Le compteur démarre à l'entrée validée et s'arrête à la sortie validée.",
        "Vous êtes prévenu 2 heures avant la fin de votre abonnement, puis à son épuisement.",
        "Heures épuisées : l'accès est coupé ; renouvelez votre forfait sur place.",
    ]:
        c.drawString(22 * mm, y, "•  " + r)
        y -= 6 * mm

    # signatures
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 78 * mm, "Signature du membre")
    c.drawString(85 * mm, 78 * mm, "Le responsable de l'atelier")
    c.setStrokeColor(colors.HexColor("#d7d9e2"))
    c.rect(20 * mm, 50 * mm, 55 * mm, 25 * mm)
    c.rect(85 * mm, 50 * mm, 55 * mm, 25 * mm)

    # QR : consultation et renouvellement
    c.drawImage(_qr(url_espace(m)), 20 * mm, 15 * mm, 28 * mm, 28 * mm)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(50 * mm, 32 * mm, "Suivre ma consommation")
    c.setFont("Helvetica", 8)
    c.setFillColor(GRIS)
    c.drawString(50 * mm, 27 * mm, "Scannez avec votre téléphone")
    c.drawImage(_qr(url_renouvellement(m)), W - 20 * mm - 28 * mm, 15 * mm, 28 * mm, 28 * mm)
    c.setFillColor(MADDER)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(W - 52 * mm, 32 * mm, "Renouveler mon abonnement")
    c.setFont("Helvetica", 8)
    c.setFillColor(GRIS)
    c.drawRightString(W - 52 * mm, 27 * mm, "Scannez ce QR code")
    c.showPage()
    c.save()
    return buf.getvalue()


def carte_pdf(m):
    """Carte de membre au format carte bancaire (85,6 x 54 mm), recto puis verso."""
    buf = io.BytesIO()
    W, H = 85.6 * mm, 54 * mm
    c = canvas.Canvas(buf, pagesize=(W, H))

    # recto
    c.setFillColor(INDIGO)
    c.rect(0, H - 11 * mm, W, 11 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    _fit(c, settings.ATELIER_NOM, "Helvetica-Bold", 11, W - 8 * mm)
    c.drawString(4 * mm, H - 7 * mm, settings.ATELIER_NOM)
    _photo(c, m, 4 * mm, 6 * mm, 20 * mm, 25 * mm)
    c.setFillColor(colors.black)
    _fit(c, m.nom, "Helvetica-Bold", 10, 34 * mm)
    c.drawString(27 * mm, 29 * mm, m.nom)
    c.setFillColor(GRIS)
    _fit(c, m.metier or "Membre", "Helvetica", 8, 34 * mm)
    c.drawString(27 * mm, 24 * mm, m.metier or "Membre")
    c.setFillColor(MADDER)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(27 * mm, 17 * mm, m.numero or "")
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 6)
    c.drawString(27 * mm, 9 * mm, "Carte personnelle — à présenter")
    c.drawString(27 * mm, 6 * mm, "à l'entrée et à la sortie")
    c.drawImage(_qr(url_membre(m)), W - 25 * mm, 5 * mm, 22 * mm, 22 * mm)
    c.showPage()

    # verso
    c.setFillColor(MADDER)
    c.rect(0, H - 11 * mm, W, 11 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(4 * mm, H - 7 * mm, "Renouveler mon abonnement")
    c.drawImage(_qr(url_renouvellement(m)), 4 * mm, 5 * mm, 30 * mm, 30 * mm)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(38 * mm, 30 * mm, "Scannez avec votre téléphone")
    c.setFont("Helvetica", 7)
    c.setFillColor(GRIS)
    c.drawString(38 * mm, 24 * mm, "pour renouveler votre forfait")
    c.drawString(38 * mm, 20 * mm, "et suivre votre temps restant.")
    c.setFont("Helvetica", 6)
    c.drawString(38 * mm, 8 * mm, f"Membre {m.numero or ''}")
    c.showPage()
    c.save()
    return buf.getvalue()
