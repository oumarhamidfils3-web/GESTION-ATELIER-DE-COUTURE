from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Abonnement, Demande, Membre, Recharge, Seance


class ErreurAtelier(Exception):
    pass


def _clore(seance, ab, par, quand, sans_carte=False, systeme=False):
    """Termine une séance et déduit le temps utilisé (plafonné au solde)."""
    reste = max(ab.total_s - ab.consomme_s, 0)
    ecoule = max(int((quand - seance.entree_at).total_seconds()), 0)
    utilise = min(ecoule, reste)
    seance.sortie_at = quand
    seance.sortie_par = par
    seance.sortie_sans_carte = sans_carte
    seance.secondes = utilise
    seance.clos_par_systeme = systeme
    seance.save()
    ab.consomme_s += utilise
    if ab.statut == Abonnement.ACTIF and ab.total_s - ab.consomme_s <= 0:
        ab.statut = Abonnement.EPUISE
        ab.epuise_le = quand
    ab.save()


def _solder_demandes(membre, type_, par):
    membre.demandes.filter(statut=Demande.ATTENTE, type=type_).update(
        statut=Demande.VALIDEE, traite_par=par, traite_le=timezone.now())


@transaction.atomic
def valider_entree(membre, par, sans_carte=False):
    if membre.seance_ouverte():
        raise ErreurAtelier(f"{membre.nom} est déjà dans l'atelier.")
    ab = membre.abonnement_actif()
    if ab is None:
        cour = membre.abonnement_courant()
        if cour and cour.statut == Abonnement.REVOQUE:
            raise ErreurAtelier("Abonnement révoqué : accès refusé.")
        raise ErreurAtelier("Heures épuisées : le membre doit renouveler son forfait.")
    if ab.restant_s() <= 0:
        raise ErreurAtelier("Heures épuisées : le membre doit renouveler son forfait.")
    seance = Seance.objects.create(
        membre=membre, abonnement=ab, entree_at=timezone.now(),
        entree_par=par, entree_sans_carte=sans_carte,
    )
    _solder_demandes(membre, Demande.ENTREE, par)
    return seance


@transaction.atomic
def valider_sortie(membre, par, sans_carte=False):
    s = membre.seance_ouverte()
    if s is None:
        raise ErreurAtelier(f"{membre.nom} n'est pas dans l'atelier.")
    _clore(s, s.abonnement, par, timezone.now(), sans_carte)
    _solder_demandes(membre, Demande.SORTIE, par)
    return s


@transaction.atomic
def ajouter_forfait(membre, forfait, par):
    """Inscription ou renouvellement : ajoute les heures à l'abonnement actif, ou en ouvre un nouveau."""
    ab = membre.abonnement_actif()
    if ab:
        ab.total_s += forfait.secondes
        ab.save()
    else:
        ab = Abonnement.objects.create(membre=membre, total_s=forfait.secondes)
    Recharge.objects.create(
        membre=membre, forfait_nom=forfait.nom, secondes=forfait.secondes,
        prix=forfait.prix, cree_par=par,
    )
    return ab


@transaction.atomic
def revoquer(membre, par, motif=""):
    ab = membre.abonnement_actif()
    if ab is None:
        raise ErreurAtelier("Aucun abonnement actif à révoquer.")
    now = timezone.now()
    s = membre.seance_ouverte()
    if s:
        _clore(s, ab, par, now)
    ab.statut = Abonnement.REVOQUE
    ab.revoque_le = now
    ab.revoque_par = par
    ab.motif = motif[:200]
    ab.save()


def cloturer_depassements():
    """Clôt les séances dont le temps est épuisé et coupe l'accès.
    Renvoie les séances clôturées par le système."""
    now = timezone.now()
    clotures = []
    for s in Seance.objects.filter(sortie_at__isnull=True).select_related("abonnement", "membre"):
        ab = s.abonnement
        reste = max(ab.total_s - ab.consomme_s, 0)
        if int((now - s.entree_at).total_seconds()) >= reste:
            with transaction.atomic():
                _clore(s, ab, None, s.entree_at + timedelta(seconds=reste), systeme=True)
            clotures.append(s)
    return clotures


# ---------------------------------------------------------------- paiements
from .models import Paiement  # noqa: E402


@transaction.atomic
def demander_renouvellement(membre, forfait, mode, reference=""):
    cour = membre.abonnement_courant()
    if cour and cour.statut == Abonnement.REVOQUE:
        raise ErreurAtelier("Abonnement révoqué : contactez l'administrateur.")
    if mode not in dict(Paiement.MODES):
        raise ErreurAtelier("Choisissez un mode de paiement.")
    from django.conf import settings
    if mode != Paiement.CAISSE and not settings.PAIEMENT_MOBILE_ACTIF:
        raise ErreurAtelier("Le paiement mobile n'est pas encore disponible : réglez à la caisse.")
    if mode != Paiement.CAISSE and not reference.strip():
        raise ErreurAtelier("Indiquez la référence de la transaction reçue par SMS.")
    membre.paiements.filter(statut=Paiement.ATTENTE).update(statut=Paiement.ANNULE)
    return Paiement.objects.create(membre=membre, forfait=forfait, mode=mode, reference=reference.strip()[:60])


@transaction.atomic
def valider_paiement(paiement, par):
    p = Paiement.objects.select_for_update().get(pk=paiement.pk)
    if p.statut != Paiement.ATTENTE:
        raise ErreurAtelier("Ce paiement a déjà été traité.")
    cour = p.membre.abonnement_courant()
    if cour and cour.statut == Abonnement.REVOQUE:
        raise ErreurAtelier("Abonnement révoqué : seul l'administrateur peut le rétablir.")
    ajouter_forfait(p.membre, p.forfait, par)
    p.statut, p.traite_par, p.traite_le = Paiement.VALIDE, par, timezone.now()
    p.save()
    return p


@transaction.atomic
def refuser_paiement(paiement, par):
    p = Paiement.objects.select_for_update().get(pk=paiement.pk)
    if p.statut != Paiement.ATTENTE:
        raise ErreurAtelier("Ce paiement a déjà été traité.")
    p.statut, p.traite_par, p.traite_le = Paiement.REFUSE, par, timezone.now()
    p.save()
    return p


# ------------------------------------------------------------------ alertes
def _admin_destinataires():
    from django.conf import settings
    from django.contrib.auth import get_user_model
    out = []
    for u in get_user_model().objects.filter(is_active=True, is_superuser=True):
        tel = getattr(getattr(u, "profil", None), "telephone", "")
        if tel:
            out.append((u.get_full_name() or u.username, tel))
    out += [("Administrateur", t) for t in settings.ADMIN_TELEPHONES]
    return out


def _responsable_destinataire(user):
    if user is None:
        return []
    tel = getattr(getattr(user, "profil", None), "telephone", "")
    return [(user.get_full_name() or user.username, tel)] if tel else []


def _diffuser(alerte, membre, valideur, texte_membre, texte_equipe):
    from .models import Envoi
    from .notifications import envoyer
    vus = set()
    cibles = [(membre.nom, membre.telephone, texte_membre)]
    for nom, tel in _responsable_destinataire(valideur) + _admin_destinataires():
        cibles.append((nom, tel, texte_equipe))
    for nom, tel, texte in cibles:
        for canal in ("sms", "whatsapp"):
            cle = (tel, canal)
            if cle in vus:
                continue
            vus.add(cle)
            ok, err = envoyer(canal, tel, texte)
            Envoi.objects.create(alerte=alerte, destinataire=nom, numero=tel, canal=canal, ok=ok, erreur=err)


def traiter_alertes():
    """À exécuter chaque minute : clôt les séances épuisées puis envoie les alertes (SMS + WhatsApp)."""
    from django.conf import settings
    from django.db import IntegrityError
    from .models import Alerte
    cloturer_depassements()
    now = timezone.now()
    nb = 0

    # 1) il reste 2 h ou moins pendant une séance en cours
    for s in Seance.objects.filter(sortie_at__isnull=True).select_related("abonnement", "membre", "entree_par"):
        ab = s.abonnement
        reste = ab.restant_s(now)
        if 0 < reste <= 7200:
            try:
                with transaction.atomic():
                    al = Alerte.objects.create(abonnement=ab, type=Alerte.DEUX_HEURES, cycle=ab.total_s)
            except IntegrityError:
                continue
            h, r = divmod(reste, 3600)
            duree = f"{h} h {r // 60:02d} min"
            _diffuser(
                al, s.membre, s.entree_par,
                f"{settings.ATELIER_NOM} : il vous reste {duree} d'abonnement. Pensez à renouveler : {settings.SITE_URL}/m/{s.membre.token}/?suite=renouveler",
                f"{settings.ATELIER_NOM} : {s.membre.nom} ({s.membre.numero}) n'a plus que {duree} d'abonnement.",
            )
            nb += 1

    # 2) heures épuisées
    for ab in Abonnement.objects.filter(statut=Abonnement.EPUISE, epuise_le__gte=now - timedelta(hours=24)).select_related("membre"):
        try:
            with transaction.atomic():
                al = Alerte.objects.create(abonnement=ab, type=Alerte.EPUISE, cycle=ab.total_s)
        except IntegrityError:
            continue
        derniere = ab.seances.select_related("entree_par").first()
        _diffuser(
            al, ab.membre, derniere.entree_par if derniere else None,
            f"{settings.ATELIER_NOM} : vos heures sont épuisées, l'accès est coupé. Renouvelez : {settings.SITE_URL}/m/{ab.membre.token}/?suite=renouveler",
            f"{settings.ATELIER_NOM} : {ab.membre.nom} ({ab.membre.numero}) a épuisé ses heures. Accès coupé.",
        )
        nb += 1
    return nb


# ------------------------------------------------- accès du membre (téléphone)
import re  # noqa: E402

MAX_ECHECS = 5
DUREE_BLOCAGE = timedelta(minutes=15)


def trouver_membre_par_numero(texte):
    """Accepte « AT-0007 », « at 7 », « 7 »."""
    chiffres = re.sub(r"\D", "", texte or "")
    if not chiffres:
        return None
    return Membre.objects.filter(numero=f"AT-{int(chiffres):04d}").first()


def connexion_membre(membre, pin):
    """Vérifie le code personnel. Après 5 erreurs, le compte est bloqué 15 minutes."""
    now = timezone.now()
    if membre.pin_bloque_jusqua and membre.pin_bloque_jusqua > now:
        raise ErreurAtelier("Trop d'essais. Réessayez dans quelques minutes ou demandez un nouveau code à un responsable.")
    if membre.verifier_pin(pin):
        if membre.pin_echecs:
            membre.pin_echecs = 0
            membre.save(update_fields=["pin_echecs"])
        return True
    membre.pin_echecs += 1
    if membre.pin_echecs >= MAX_ECHECS:
        membre.pin_echecs = 0
        membre.pin_bloque_jusqua = now + DUREE_BLOCAGE
    membre.save(update_fields=["pin_echecs", "pin_bloque_jusqua"])
    return False


@transaction.atomic
def demander_entree(membre):
    cloturer_depassements()
    if membre.seance_ouverte():
        raise ErreurAtelier("Vous êtes déjà dans l'atelier.")
    if membre.demande_en_attente():
        raise ErreurAtelier("Une demande est déjà en attente de validation.")
    ab = membre.abonnement_actif()
    if ab is None:
        cour = membre.abonnement_courant()
        if cour and cour.statut == Abonnement.REVOQUE:
            raise ErreurAtelier("Votre abonnement est révoqué. Rapprochez-vous de l'administrateur.")
        raise ErreurAtelier("Vos heures sont épuisées : renouvelez votre forfait.")
    if ab.restant_s() <= 0:
        raise ErreurAtelier("Vos heures sont épuisées : renouvelez votre forfait.")
    return Demande.objects.create(membre=membre, type=Demande.ENTREE)


@transaction.atomic
def demander_sortie(membre):
    cloturer_depassements()
    if not membre.seance_ouverte():
        raise ErreurAtelier("Vous n'êtes pas dans l'atelier.")
    if membre.demande_en_attente():
        raise ErreurAtelier("Une demande est déjà en attente de validation.")
    return Demande.objects.create(membre=membre, type=Demande.SORTIE)


def annuler_demande(membre):
    n = membre.demandes.filter(statut=Demande.ATTENTE).update(statut=Demande.ANNULEE, traite_le=timezone.now())
    return n > 0


@transaction.atomic
def traiter_demande(demande, par, accepter):
    """Un responsable ou l'administrateur valide ou refuse la demande du membre.
    Entrée : le compteur démarre à la validation. Sortie : il s'arrête à l'heure où le membre a scanné."""
    d = Demande.objects.select_for_update().select_related("membre").get(pk=demande.pk)
    if d.statut != Demande.ATTENTE:
        raise ErreurAtelier("Cette demande a déjà été traitée.")
    now = timezone.now()
    if not accepter:
        d.statut, d.traite_par, d.traite_le = Demande.REFUSEE, par, now
        d.save()
        return d
    m = d.membre
    if d.type == Demande.ENTREE:
        valider_entree(m, par)  # lève une erreur si refusé (révoqué, épuisé, déjà dans l'atelier)
    else:
        s = m.seance_ouverte()
        if s is None:  # déjà clôturée (heures épuisées) : rien à faire
            d.statut, d.traite_le = Demande.ANNULEE, now
            d.save()
            return d
        _clore(s, s.abonnement, par, max(d.cree_le, s.entree_at))
    d.refresh_from_db()
    d.statut, d.traite_par, d.traite_le = Demande.VALIDEE, par, now
    d.save()
    return d
