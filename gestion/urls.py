from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("connexion/", auth_views.LoginView.as_view(template_name="gestion/login.html"), name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    path("membres/", views.membres, name="membres"),
    path("membres/nouveau/", views.membre_nouveau, name="membre_nouveau"),
    path("membres/<int:pk>/", views.membre_detail, name="membre_detail"),
    path("membres/<int:pk>/photo/", views.photo_membre, name="photo_membre"),
    path("membres/<int:pk>/fiche.pdf", views.fiche_pdf, name="fiche_pdf"),
    path("membres/<int:pk>/carte.pdf", views.carte_pdf, name="carte_pdf"),
    path("membres/<int:pk>/forfait/", views.membre_forfait, name="membre_forfait"),
    path("membres/<int:pk>/valider/", views.valider, name="valider"),
    path("membres/<int:pk>/revoquer/", views.membre_revoquer, name="membre_revoquer"),
    path("scan/<uuid:token>/", views.scan, name="scan"),
    path("atelier/", views.atelier_acces, name="atelier_acces"),
    path("m/<uuid:token>/", views.membre_acces, name="membre_acces"),
    path("espace/", views.espace, name="espace"),
    path("espace/forfait/", views.espace_forfait, name="espace_forfait"),
    path("espace/renouveler/", views.espace_renouveler, name="espace_renouveler"),
    path("espace/entree/", views.espace_demande, {"type_": "entree"}, name="espace_entree"),
    path("espace/sortie/", views.espace_demande, {"type_": "sortie"}, name="espace_sortie"),
    path("espace/annuler/", views.espace_annuler, name="espace_annuler"),
    path("espace/mot-de-passe/", views.espace_mot_de_passe, name="espace_mot_de_passe"),
    path("espace/quitter/", views.espace_quitter, name="espace_quitter"),
    path("demandes/<int:pk>/<str:action>/", views.demande_traiter, name="demande_traiter"),
    path("membres/<int:pk>/code/", views.membre_pin, name="membre_pin"),
    path("membres/<int:pk>/code/masquer/", views.membre_pin_masquer, name="membre_pin_masquer"),
    path("affiche.pdf", views.affiche_pdf, name="affiche_pdf"),
    path("paiements/<int:pk>/<str:action>/", views.paiement_traiter, name="paiement_traiter"),
    path("caisse/", views.caisse, name="caisse"),
    path("responsables/", views.responsables, name="responsables"),
    path("responsables/<int:pk>/basculer/", views.responsable_basculer, name="responsable_basculer"),
]
