from django.contrib import admin

from .models import Abonnement, Alerte, Demande, Envoi, Forfait, Membre, Paiement, Profil, Recharge, Seance

admin.site.register(Forfait)
admin.site.register(Profil)
admin.site.register(Membre)
admin.site.register(Abonnement)
admin.site.register(Recharge)
admin.site.register(Seance)
admin.site.register(Paiement)
admin.site.register(Alerte)
admin.site.register(Envoi)
admin.site.register(Demande)


# L'espace d'administration est réservé au seul administrateur : ni un responsable, ni un membre n'y entrent.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser
