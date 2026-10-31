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
    path("m/<uuid:token>/", views.espace_membre, name="espace_membre"),
    path("m/<uuid:token>/renouveler/", views.renouveler, name="renouveler"),
    path("paiements/<int:pk>/<str:action>/", views.paiement_traiter, name="paiement_traiter"),
    path("caisse/", views.caisse, name="caisse"),
    path("responsables/", views.responsables, name="responsables"),
    path("responsables/<int:pk>/basculer/", views.responsable_basculer, name="responsable_basculer"),
]
