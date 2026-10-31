import time

from django.core.management.base import BaseCommand

from gestion import services


class Command(BaseCommand):
    help = "Clôt les séances épuisées et envoie les alertes SMS + WhatsApp (à lancer chaque minute)."

    def add_arguments(self, parser):
        parser.add_argument("--boucle", action="store_true", help="Tourne en continu (toutes les 30 s).")

    def handle(self, *args, **opts):
        while True:
            n = services.traiter_alertes()
            if n:
                self.stdout.write(f"{n} alerte(s) traitée(s).")
            if not opts["boucle"]:
                break
            time.sleep(30)
