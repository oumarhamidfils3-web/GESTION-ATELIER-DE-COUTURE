from django.contrib import admin

from .models import Abonnement, Alerte, Envoi, Forfait, Membre, Paiement, Profil, Recharge, Seance

admin.site.register(Forfait)
admin.site.register(Profil)
admin.site.register(Membre)
admin.site.register(Abonnement)
admin.site.register(Recharge)
admin.site.register(Seance)
admin.site.register(Paiement)
admin.site.register(Alerte)
admin.site.register(Envoi)
