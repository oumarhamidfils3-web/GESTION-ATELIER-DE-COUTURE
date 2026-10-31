import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Profil(models.Model):
    """Un utilisateur ayant un profil est un responsable de l'atelier.
    L'administrateur est le superutilisateur Django."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profil")
    telephone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Forfait(models.Model):
    nom = models.CharField(max_length=80)
    heures = models.DecimalField(max_digits=6, decimal_places=2)
    prix = models.PositiveIntegerField(default=0, help_text="Prix en FCFA")
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["heures"]

    def __str__(self):
        return f"{self.nom} — {self.heures:g} h — {self.prix} FCFA"

    @property
    def secondes(self):
        return int(self.heures * 3600)


class Membre(models.Model):
    numero = models.CharField(max_length=12, unique=True, null=True, blank=True, editable=False)
    nom = models.CharField("Nom complet", max_length=120)
    telephone = models.CharField("Téléphone", max_length=30)
    metier = models.CharField("Métier", max_length=80, blank=True)
    adresse = models.CharField(max_length=160, blank=True)
    photo_data = models.BinaryField(null=True, blank=True, editable=False)  # JPEG réduit, stocké en base
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} ({self.numero})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.numero:
            self.numero = f"AT-{self.pk:04d}"
            super().save(update_fields=["numero"])

    def seance_ouverte(self):
        return self.seances.filter(sortie_at__isnull=True).first()

    def abonnement_actif(self):
        return self.abonnements.filter(statut=Abonnement.ACTIF).order_by("-cree_le").first()

    def abonnement_courant(self):
        return self.abonnements.order_by("-cree_le").first()

    @property
    def etat(self):
        ab = self.abonnement_courant()
        if ab is None:
            return "aucun"
        if ab.statut == Abonnement.ACTIF and ab.restant_s() <= 0:
            return Abonnement.EPUISE
        return ab.statut


class Abonnement(models.Model):
    ACTIF, EPUISE, REVOQUE = "actif", "epuise", "revoque"
    STATUTS = [(ACTIF, "Actif"), (EPUISE, "Épuisé"), (REVOQUE, "Révoqué")]

    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name="abonnements")
    total_s = models.PositiveIntegerField(default=0)
    consomme_s = models.PositiveIntegerField(default=0)
    statut = models.CharField(max_length=10, choices=STATUTS, default=ACTIF)
    cree_le = models.DateTimeField(auto_now_add=True)
    epuise_le = models.DateTimeField(null=True, blank=True)
    revoque_le = models.DateTimeField(null=True, blank=True)
    revoque_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    motif = models.CharField(max_length=200, blank=True)

    def restant_s(self, now=None):
        """Temps restant en secondes, séance en cours comprise."""
        now = now or timezone.now()
        reste = self.total_s - self.consomme_s
        if self.statut == self.ACTIF:
            s = self.seances.filter(sortie_at__isnull=True).first()
            if s:
                reste -= int((now - s.entree_at).total_seconds())
        return max(reste, 0)

    def __str__(self):
        return f"{self.membre} — {self.get_statut_display()}"


class Recharge(models.Model):
    """Historique des forfaits achetés (inscription et renouvellements)."""
    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name="recharges")
    forfait_nom = models.CharField(max_length=80)
    secondes = models.PositiveIntegerField()
    prix = models.PositiveIntegerField(default=0)
    cree_le = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["cree_le"]


class Seance(models.Model):
    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name="seances")
    abonnement = models.ForeignKey(Abonnement, on_delete=models.CASCADE, related_name="seances")
    entree_at = models.DateTimeField()
    entree_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    entree_sans_carte = models.BooleanField(default=False)
    sortie_at = models.DateTimeField(null=True, blank=True)
    sortie_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sortie_sans_carte = models.BooleanField(default=False)
    secondes = models.PositiveIntegerField(default=0)
    clos_par_systeme = models.BooleanField(default=False)

    class Meta:
        ordering = ["-entree_at"]


class Paiement(models.Model):
    """Demande de renouvellement faite par le membre via son QR ; validée par un responsable ou l'administrateur."""
    ORANGE, MOMO, CAISSE = "orange", "momo", "caisse"
    MODES = [(ORANGE, "Orange Money"), (MOMO, "Mobile Money"), (CAISSE, "Caisse")]
    ATTENTE, VALIDE, REFUSE, ANNULE = "attente", "valide", "refuse", "annule"
    STATUTS = [(ATTENTE, "En attente"), (VALIDE, "Validé"), (REFUSE, "Refusé"), (ANNULE, "Annulé")]

    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name="paiements")
    forfait = models.ForeignKey(Forfait, on_delete=models.PROTECT, related_name="+")
    mode = models.CharField(max_length=10, choices=MODES)
    reference = models.CharField("Référence de la transaction", max_length=60, blank=True)
    statut = models.CharField(max_length=10, choices=STATUTS, default=ATTENTE)
    cree_le = models.DateTimeField(auto_now_add=True)
    traite_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    traite_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]


class Alerte(models.Model):
    """Une alerte par abonnement, par type et par « cycle » (le cycle change à chaque renouvellement)."""
    DEUX_HEURES, EPUISE = "2h", "epuise"
    TYPES = [(DEUX_HEURES, "2 heures avant la fin"), (EPUISE, "Heures épuisées")]
    abonnement = models.ForeignKey(Abonnement, on_delete=models.CASCADE, related_name="alertes")
    type = models.CharField(max_length=10, choices=TYPES)
    cycle = models.PositiveIntegerField()
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("abonnement", "type", "cycle")]


class Envoi(models.Model):
    alerte = models.ForeignKey(Alerte, on_delete=models.CASCADE, related_name="envois")
    destinataire = models.CharField(max_length=120)
    numero = models.CharField(max_length=30)
    canal = models.CharField(max_length=10)  # sms | whatsapp
    ok = models.BooleanField(default=False)
    erreur = models.CharField(max_length=300, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)
