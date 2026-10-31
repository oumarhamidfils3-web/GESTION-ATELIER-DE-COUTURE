import csv
from datetime import date, datetime, timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import pdf, services
from .forms import MembreForm, ResponsableForm
from .models import Abonnement, Forfait, Membre, Paiement, Profil, Recharge, Seance

User = get_user_model()


def est_admin(u):
    return u.is_authenticated and u.is_active and u.is_superuser


def est_responsable(u):
    if not (u.is_authenticated and u.is_active):
        return False
    return u.is_superuser or hasattr(u, "profil")


def _protege(test):
    def deco(view):
        @wraps(view)
        def wrapper(request, *a, **k):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not test(request.user):
                raise PermissionDenied
            return view(request, *a, **k)
        return wrapper
    return deco


responsable_requis = _protege(est_responsable)
admin_requis = _protege(est_admin)


def _nom(u):
    return u.get_full_name() or u.username


def _retour(request, defaut):
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(defaut)


def _ligne(m):
    ab = m.abonnement_courant()
    ouverte = m.seance_ouverte()
    return {
        "m": m, "ab": ab, "etat": m.etat, "ouverte": ouverte,
        "restant": ab.restant_s() if ab else 0,
    }


@responsable_requis
def accueil(request):
    services.cloturer_depassements()
    now = timezone.now()
    ouvertes = (Seance.objects.filter(sortie_at__isnull=True)
                .select_related("membre", "abonnement", "entree_par").order_by("entree_at"))
    presents = [{"s": s, "restant": s.abonnement.restant_s(now), "alerte": s.abonnement.restant_s(now) <= 7200}
                for s in ouvertes]
    epuises = (Seance.objects.filter(clos_par_systeme=True, sortie_at__gte=now - timedelta(hours=24))
               .select_related("membre", "entree_par").order_by("-sortie_at"))
    return render(request, "gestion/accueil.html", {
        "presents": presents, "epuises": epuises,
        "paiements": Paiement.objects.filter(statut=Paiement.ATTENTE).select_related("membre", "forfait").order_by("cree_le"),
        "nb_membres": Membre.objects.count(),
        "sans_forfait": not Forfait.objects.filter(actif=True).exists(),
    })


@responsable_requis
def membres(request):
    services.cloturer_depassements()
    q = request.GET.get("q", "").strip()
    qs = Membre.objects.all()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(numero__icontains=q) | Q(telephone__icontains=q))
    return render(request, "gestion/membres.html", {"lignes": [_ligne(m) for m in qs[:100]], "q": q})


@responsable_requis
def membre_nouveau(request):
    form = MembreForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        m = form.save(commit=False)
        m.cree_par = request.user
        m.save()
        services.ajouter_forfait(m, form.cleaned_data["forfait"], request.user)
        messages.success(request, f"{m.nom} est inscrit(e) sous le numéro {m.numero}.")
        return redirect("membre_detail", pk=m.pk)
    return render(request, "gestion/membre_form.html", {"form": form})


@responsable_requis
def membre_detail(request, pk):
    services.cloturer_depassements()
    m = get_object_or_404(Membre, pk=pk)
    return render(request, "gestion/membre_detail.html", {
        "l": _ligne(m), "m": m,
        "seances": m.seances.all()[:30],
        "recharges": m.recharges.order_by("-cree_le")[:10],
        "forfaits": Forfait.objects.filter(actif=True),
        "url_scan": pdf.url_membre(m),
    })


@responsable_requis
def fiche_pdf(request, pk):
    m = get_object_or_404(Membre, pk=pk)
    rep = HttpResponse(pdf.fiche_pdf(m), content_type="application/pdf")
    rep["Content-Disposition"] = f'inline; filename="fiche-{m.numero}.pdf"'
    return rep


@responsable_requis
def carte_pdf(request, pk):
    m = get_object_or_404(Membre, pk=pk)
    rep = HttpResponse(pdf.carte_pdf(m), content_type="application/pdf")
    rep["Content-Disposition"] = f'inline; filename="carte-{m.numero}.pdf"'
    return rep


@responsable_requis
@require_POST
def membre_forfait(request, pk):
    m = get_object_or_404(Membre, pk=pk)
    f = get_object_or_404(Forfait, pk=request.POST.get("forfait"), actif=True)
    cour = m.abonnement_courant()
    if cour and cour.statut == Abonnement.REVOQUE and not est_admin(request.user):
        messages.error(request, "Abonnement révoqué : seul l'administrateur peut le rétablir.")
    else:
        services.ajouter_forfait(m, f, request.user)
        messages.success(request, f"{f.heures:g} h ajoutées pour {m.nom}.")
    return _retour(request, reverse("membre_detail", args=[m.pk]))


@responsable_requis
@require_POST
def valider(request, pk):
    m = get_object_or_404(Membre, pk=pk)
    sans_carte = request.POST.get("sans_carte") == "1"
    services.cloturer_depassements()
    try:
        if m.seance_ouverte():
            s = services.valider_sortie(m, request.user, sans_carte)
            h, r = divmod(s.secondes, 3600)
            messages.success(request, f"Sortie validée : {m.nom} ({h} h {r // 60:02d} min utilisées).")
        else:
            services.valider_entree(m, request.user, sans_carte)
            messages.success(request, f"Entrée validée : {m.nom}. Le compteur a démarré.")
    except services.ErreurAtelier as e:
        messages.error(request, str(e))
    return _retour(request, reverse("membre_detail", args=[m.pk]))


@admin_requis
@require_POST
def membre_revoquer(request, pk):
    m = get_object_or_404(Membre, pk=pk)
    try:
        services.revoquer(m, request.user, request.POST.get("motif", ""))
        messages.success(request, f"L'abonnement de {m.nom} est révoqué.")
    except services.ErreurAtelier as e:
        messages.error(request, str(e))
    return redirect("membre_detail", pk=m.pk)


def scan(request, token):
    """Cible du QR de la carte. Le responsable valide ; toute autre personne voit son espace membre."""
    m = get_object_or_404(Membre, token=token)
    if not est_responsable(request.user):
        return redirect("espace_membre", token=token)
    services.cloturer_depassements()
    return render(request, "gestion/scan.html", {"l": _ligne(m), "m": m})


def espace_membre(request, token):
    services.cloturer_depassements()
    m = get_object_or_404(Membre, token=token)
    l = _ligne(m)
    return render(request, "gestion/espace_membre.html", {
        "l": l, "m": m, "seances": m.seances.all()[:20],
        "total": l["ab"].total_s if l["ab"] else 0,
        "consomme": (l["ab"].total_s - l["restant"]) if l["ab"] else 0,
    })


def renouveler(request, token):
    """Page ouverte par le QR de renouvellement : le membre choisit son forfait et son mode de paiement."""
    m = get_object_or_404(Membre, token=token)
    forfaits = Forfait.objects.filter(actif=True)
    if request.method == "POST":
        f = forfaits.filter(pk=request.POST.get("forfait")).first()
        try:
            if f is None:
                raise services.ErreurAtelier("Choisissez un forfait.")
            services.demander_renouvellement(m, f, request.POST.get("mode", ""), request.POST.get("reference", ""))
            messages.success(request, "Demande envoyée. Un responsable va valider votre paiement.")
            return redirect("renouveler", token=token)
        except services.ErreurAtelier as e:
            messages.error(request, str(e))
    return render(request, "gestion/renouveler.html", {
        "m": m, "l": _ligne(m), "forfaits": forfaits,
        "attente": m.paiements.filter(statut=Paiement.ATTENTE).select_related("forfait").first(),
        "dernier": m.paiements.exclude(statut=Paiement.ATTENTE).select_related("forfait").first(),
        "mobile_actif": settings.PAIEMENT_MOBILE_ACTIF, "orange": settings.ORANGE_MONEY_NUMERO, "momo": settings.MOMO_NUMERO,
    })


@responsable_requis
@require_POST
def paiement_traiter(request, pk, action):
    p = get_object_or_404(Paiement, pk=pk)
    try:
        if action == "valider":
            services.valider_paiement(p, request.user)
            messages.success(request, f"Paiement validé : {p.forfait.heures:g} h ajoutées pour {p.membre.nom}.")
        else:
            services.refuser_paiement(p, request.user)
            messages.success(request, f"Paiement de {p.membre.nom} refusé.")
    except services.ErreurAtelier as e:
        messages.error(request, str(e))
    return _retour(request, reverse("accueil"))


@admin_requis
def responsables(request):
    form = ResponsableForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        u = User.objects.create_user(username=d["identifiant"], password=d["mot_de_passe"], first_name=d["nom_complet"])
        Profil.objects.create(user=u, telephone=d["telephone"])
        messages.success(request, f"Compte responsable créé pour {d['nom_complet']}.")
        return redirect("responsables")
    return render(request, "gestion/responsables.html", {
        "form": form, "liste": Profil.objects.select_related("user").order_by("user__first_name"),
    })


@admin_requis
@require_POST
def responsable_basculer(request, pk):
    p = get_object_or_404(Profil, pk=pk)
    p.user.is_active = not p.user.is_active
    p.user.save(update_fields=["is_active"])
    messages.success(request, f"Accès de {_nom(p.user)} {'rétabli' if p.user.is_active else 'retiré'}.")
    return redirect("responsables")


def _bornes(d):
    """Début (inclus) et fin (exclue) d'une journée locale."""
    debut = timezone.make_aware(datetime.combine(d, datetime.min.time()))
    return debut, debut + timedelta(days=1)


@responsable_requis
def caisse(request):
    """Recettes : l'administrateur voit tout, un responsable ne voit que ses propres encaissements."""
    try:
        jour = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        jour = timezone.localdate()
    base = Recharge.objects.select_related("membre", "cree_par")
    if not est_admin(request.user):
        base = base.filter(cree_par=request.user)

    def total(debut, fin):
        r = base.filter(cree_le__gte=debut, cree_le__lt=fin).aggregate(t=Sum("prix"), n=Count("id"))
        return {"total": r["t"] or 0, "nb": r["n"]}

    d0, d1 = _bornes(jour)
    sem_debut = jour - timedelta(days=jour.weekday())
    mois_debut = jour.replace(day=1)
    periodes = [
        ("Jour", jour.strftime("%d/%m/%Y"), total(d0, d1)),
        ("Semaine", f"depuis le {sem_debut.strftime('%d/%m')}", total(_bornes(sem_debut)[0], d1)),
        ("Mois", jour.strftime("%m/%Y"), total(_bornes(mois_debut)[0], d1)),
    ]
    operations = base.filter(cree_le__gte=d0, cree_le__lt=d1).order_by("cree_le")

    if request.GET.get("export") == "csv" and est_admin(request.user):
        rep = HttpResponse(content_type="text/csv; charset=utf-8")
        rep["Content-Disposition"] = f'attachment; filename="caisse-{jour.isoformat()}.csv"'
        rep.write("\ufeff")
        w = csv.writer(rep, delimiter=";")
        w.writerow(["Heure", "Membre", "Numéro", "Forfait", "Prix (FCFA)", "Encaissé par"])
        for o in operations:
            w.writerow([timezone.localtime(o.cree_le).strftime("%H:%M"), o.membre.nom, o.membre.numero,
                        o.forfait_nom, o.prix, _nom(o.cree_par) if o.cree_par else ""])
        return rep

    par_responsable = []
    if est_admin(request.user):
        def agreg(debut, fin):
            qs = (base.filter(cree_le__gte=debut, cree_le__lt=fin).values("cree_par", "cree_par__first_name", "cree_par__username")
                  .annotate(t=Sum("prix"), n=Count("id")))
            return {r["cree_par"]: r for r in qs}
        j, sm = agreg(d0, d1), agreg(_bornes(sem_debut)[0], d1)
        for uid in sorted(set(j) | set(sm), key=lambda k: -(sm.get(k) or j.get(k))["t"]):
            ref = sm.get(uid) or j.get(uid)
            par_responsable.append({
                "nom": ref["cree_par__first_name"] or ref["cree_par__username"] or "Inconnu",
                "jour": (j.get(uid) or {}).get("t", 0), "semaine": (sm.get(uid) or {}).get("t", 0),
            })
    return render(request, "gestion/caisse.html", {
        "jour": jour, "veille": jour - timedelta(days=1), "lendemain": jour + timedelta(days=1),
        "aujourdhui": timezone.localdate(), "periodes": periodes, "operations": operations,
        "par_responsable": par_responsable,
    })
