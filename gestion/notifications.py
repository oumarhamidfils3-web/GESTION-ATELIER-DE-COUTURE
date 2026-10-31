"""Envoi des SMS et messages WhatsApp.

NOTIF_BACKEND=console : écrit les messages dans les journaux (essais, sans coût).
NOTIF_BACKEND=twilio  : envoi réel via l'API REST de Twilio (SMS et WhatsApp).
"""
import base64
import logging
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger("gestion.notifications")


def normaliser(numero):
    """Met un numéro au format international (+237...). Renvoie '' si inutilisable."""
    n = "".join(ch for ch in (numero or "") if ch.isdigit() or ch == "+")
    if not n:
        return ""
    if n.startswith("00"):
        n = "+" + n[2:]
    if n.startswith("+"):
        return n
    if n.startswith(settings.PAYS_INDICATIF):
        return "+" + n
    return "+" + settings.PAYS_INDICATIF + n.lstrip("0")


def _twilio(expediteur, destinataire, texte):
    sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
    if not (sid and token and expediteur):
        raise RuntimeError("Configuration Twilio incomplète.")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"From": expediteur, "To": destinataire, "Body": texte}).encode()
    req = urllib.request.Request(url, data=data)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
    with urllib.request.urlopen(req, timeout=15) as r:
        if r.status >= 300:
            raise RuntimeError(f"Twilio a répondu {r.status}")


def envoyer(canal, numero, texte):
    """Envoie un message. Renvoie (ok, erreur)."""
    dest = normaliser(numero)
    if not dest:
        return False, "Numéro manquant ou invalide."
    try:
        if settings.NOTIF_BACKEND == "twilio":
            if canal == "whatsapp":
                _twilio("whatsapp:" + normaliser(settings.TWILIO_WHATSAPP_FROM), "whatsapp:" + dest, texte)
            else:
                _twilio(normaliser(settings.TWILIO_SMS_FROM), dest, texte)
        else:
            log.warning("[%s -> %s] %s", canal, dest, texte)
        return True, ""
    except Exception as e:  # l'échec d'un envoi ne doit jamais bloquer l'atelier
        return False, str(e)[:300]
