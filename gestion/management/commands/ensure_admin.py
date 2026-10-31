import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crée l'administrateur à partir de ADMIN_USERNAME et ADMIN_PASSWORD s'il n'existe pas encore."

    def handle(self, *args, **opts):
        nom, mdp = os.environ.get("ADMIN_USERNAME"), os.environ.get("ADMIN_PASSWORD")
        if not (nom and mdp):
            self.stdout.write("ADMIN_USERNAME / ADMIN_PASSWORD absents : aucun administrateur créé.")
            return
        User = get_user_model()
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Un administrateur existe déjà.")
            return
        User.objects.create_superuser(username=nom, password=mdp, first_name=os.environ.get("ADMIN_NOM", "Administrateur"))
        self.stdout.write(f"Administrateur « {nom} » créé.")
