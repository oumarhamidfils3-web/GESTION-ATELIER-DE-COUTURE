import logging
import os
import threading
import time

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "atelier.settings")
application = get_wsgi_application()

# ALERTES_AUTO=1 : le service envoie lui-même les alertes (aucun second service à payer).
# À utiliser avec UN seul processus gunicorn (--workers 1).
if os.environ.get("ALERTES_AUTO") == "1":
    def _boucle():
        from gestion import services
        time.sleep(20)
        while True:
            try:
                services.traiter_alertes()
            except Exception:
                logging.getLogger("gestion").exception("Échec du traitement des alertes")
            time.sleep(30)

    threading.Thread(target=_boucle, daemon=True, name="alertes").start()
