from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Abonnement, Forfait, Membre, Profil

User = get_user_model()


class AtelierTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="x", first_name="Admin")
        self.resp = User.objects.create_user("resp", password="x", first_name="Resp")
        Profil.objects.create(user=self.resp)
        self.forfait = Forfait.objects.create(nom="10 heures", heures=Decimal("10"), prix=5000)
        self.m = Membre.objects.create(nom="Awa Bello", telephone="670000000", metier="Couturière", cree_par=self.resp)
        services.ajouter_forfait(self.m, self.forfait, self.resp)

    def test_numero_et_forfait(self):
        self.assertEqual(self.m.numero, f"AT-{self.m.pk:04d}")
        self.assertEqual(self.m.abonnement_actif().total_s, 36000)

    def test_entree_sortie_et_decompte(self):
        s = services.valider_entree(self.m, self.resp)
        s.entree_at = timezone.now() - timedelta(hours=2)
        s.save()
        services.valider_sortie(self.m, self.resp)
        ab = self.m.abonnement_actif()
        self.assertAlmostEqual(ab.consomme_s, 7200, delta=3)
        self.assertAlmostEqual(ab.restant_s(), 28800, delta=3)

    def test_double_entree_refusee(self):
        services.valider_entree(self.m, self.resp)
        with self.assertRaises(services.ErreurAtelier):
            services.valider_entree(self.m, self.resp)

    def test_epuisement_coupe_acces(self):
        s = services.valider_entree(self.m, self.resp)
        s.entree_at = timezone.now() - timedelta(hours=11)
        s.save()
        clotures = services.cloturer_depassements()
        self.assertEqual(len(clotures), 1)
        ab = self.m.abonnements.first()
        self.assertEqual(ab.statut, Abonnement.EPUISE)
        self.assertEqual(ab.consomme_s, 36000)
        self.assertEqual(self.m.etat, "epuise")
        with self.assertRaises(services.ErreurAtelier):
            services.valider_entree(self.m, self.resp)
        # renouvellement séance tenante
        services.ajouter_forfait(self.m, self.forfait, self.resp)
        services.valider_entree(self.m, self.resp)

    def test_revocation(self):
        services.valider_entree(self.m, self.resp)
        services.revoquer(self.m, self.admin, "Impayé")
        self.assertEqual(self.m.etat, "revoque")
        self.assertIsNone(self.m.seance_ouverte())
        with self.assertRaises(services.ErreurAtelier):
            services.valider_entree(self.m, self.resp)

    def test_pdfs_et_pages(self):
        self.client.force_login(self.resp)
        for name in ("fiche_pdf", "carte_pdf"):
            r = self.client.get(reverse(name, args=[self.m.pk]))
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.content.startswith(b"%PDF"))
        for name in ("accueil", "membres", "membre_nouveau"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse("membre_detail", args=[self.m.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("scan", args=[self.m.token])).status_code, 200)

    def test_scan_membre_voit_son_espace(self):
        r = self.client.get(reverse("scan", args=[self.m.token]))
        self.assertRedirects(r, reverse("espace_membre", args=[self.m.token]))
        self.assertEqual(self.client.get(reverse("espace_membre", args=[self.m.token])).status_code, 200)
        self.assertEqual(self.client.get(reverse("renouveler", args=[self.m.token])).status_code, 200)

    def test_validation_via_vue_et_roles(self):
        self.client.force_login(self.resp)
        self.client.post(reverse("valider", args=[self.m.pk]), {"sans_carte": "1"})
        self.assertIsNotNone(self.m.seance_ouverte())
        self.assertTrue(self.m.seances.first().entree_sans_carte)
        # un responsable ne peut ni révoquer ni gérer les responsables
        self.assertEqual(self.client.post(reverse("membre_revoquer", args=[self.m.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("responsables")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("responsables")).status_code, 200)
        self.client.post(reverse("membre_revoquer", args=[self.m.pk]), {"motif": "test"})
        self.assertEqual(self.m.etat, "revoque")

    def test_acces_retire(self):
        self.resp.is_active = False
        self.resp.save()
        self.client.force_login(self.resp)
        self.assertNotEqual(self.client.get(reverse("accueil")).status_code, 200)

    def test_inscription_via_formulaire(self):
        self.client.force_login(self.resp)
        r = self.client.post(reverse("membre_nouveau"), {
            "nom": "Hamidou Ali", "telephone": "699111222", "metier": "Tailleur",
            "adresse": "Maroua", "forfait": self.forfait.pk,
        })
        self.assertEqual(r.status_code, 302)
        n = Membre.objects.get(nom="Hamidou Ali")
        self.assertEqual(n.abonnement_actif().total_s, 36000)


from django.test import override_settings  # noqa: E402

from .models import Alerte, Envoi, Paiement  # noqa: E402


@override_settings(ADMIN_TELEPHONES=["677000001"], PAIEMENT_MOBILE_ACTIF=True)
class BlocDeuxTests(AtelierTests):
    def setUp(self):
        super().setUp()
        self.resp.profil.telephone = "699000002"
        self.resp.profil.save()
        self.m.telephone = "670000009"
        self.m.save()

    def test_alerte_deux_heures_sms_et_whatsapp_sans_doublon(self):
        s = services.valider_entree(self.m, self.resp)
        s.entree_at = timezone.now() - timedelta(hours=8, minutes=30)
        s.save()
        self.assertEqual(services.traiter_alertes(), 1)
        al = Alerte.objects.get(type="2h")
        envois = al.envois.all()
        self.assertEqual({(e.numero, e.canal) for e in envois}, {
            ("670000009", "sms"), ("670000009", "whatsapp"),
            ("699000002", "sms"), ("699000002", "whatsapp"),
            ("677000001", "sms"), ("677000001", "whatsapp")})
        self.assertTrue(all(e.ok for e in envois))
        self.assertEqual(services.traiter_alertes(), 0)  # pas de doublon

    def test_alerte_epuisement_et_nouveau_cycle(self):
        s = services.valider_entree(self.m, self.resp)
        s.entree_at = timezone.now() - timedelta(hours=11)
        s.save()
        services.traiter_alertes()
        self.assertTrue(Alerte.objects.filter(type="epuise").exists())
        self.assertEqual(Alerte.objects.filter(type="epuise").first().envois.count(), 6)
        # renouvellement puis nouvelle séance : une nouvelle alerte 2 h est possible
        services.ajouter_forfait(self.m, self.forfait, self.resp)
        s2 = services.valider_entree(self.m, self.resp)
        s2.entree_at = timezone.now() - timedelta(hours=8, minutes=30)
        s2.save()
        self.assertEqual(services.traiter_alertes(), 1)

    def test_pas_d_alerte_hors_seance_ni_loin_de_la_fin(self):
        services.valider_entree(self.m, self.resp)
        self.assertEqual(services.traiter_alertes(), 0)

    def test_renouvellement_caisse_puis_validation(self):
        url = reverse("renouveler", args=[self.m.token])
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        self.assertEqual(r.status_code, 302)
        p = Paiement.objects.get()
        self.assertEqual(p.statut, "attente")
        self.assertEqual(self.m.abonnement_actif().total_s, 36000)  # rien d'ajouté avant validation
        self.client.force_login(self.resp)
        self.assertContains(self.client.get(reverse("accueil")), "Paiements à valider")
        self.client.post(reverse("paiement_traiter", args=[p.pk, "valider"]))
        p.refresh_from_db()
        self.assertEqual(p.statut, "valide")
        self.assertEqual(p.traite_par, self.resp)
        self.assertEqual(self.m.abonnement_actif().total_s, 72000)
        # double validation sans effet
        self.client.post(reverse("paiement_traiter", args=[p.pk, "valider"]))
        self.assertEqual(self.m.abonnement_actif().total_s, 72000)

    def test_mobile_money_exige_reference_et_refus(self):
        url = reverse("renouveler", args=[self.m.token])
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "orange"})
        self.assertEqual(Paiement.objects.count(), 0)
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "momo", "reference": "MP123"})
        p = Paiement.objects.get()
        self.assertEqual(p.reference, "MP123")
        self.client.force_login(self.admin)
        self.client.post(reverse("paiement_traiter", args=[p.pk, "refuser"]))
        p.refresh_from_db()
        self.assertEqual(p.statut, "refuse")
        self.assertEqual(self.m.abonnement_actif().total_s, 36000)

    def test_nouvelle_demande_annule_la_precedente(self):
        url = reverse("renouveler", args=[self.m.token])
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        self.assertEqual(Paiement.objects.filter(statut="attente").count(), 1)
        self.assertEqual(Paiement.objects.filter(statut="annule").count(), 1)

    def test_renouvellement_membre_epuise_reactive_acces(self):
        s = services.valider_entree(self.m, self.resp)
        s.entree_at = timezone.now() - timedelta(hours=11)
        s.save()
        services.cloturer_depassements()
        url = reverse("renouveler", args=[self.m.token])
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        p = Paiement.objects.get()
        services.valider_paiement(p, self.resp)
        services.valider_entree(self.m, self.resp)  # l'accès est rétabli

    def test_membre_revoque_ne_peut_pas_renouveler(self):
        services.revoquer(self.m, self.admin, "x")
        url = reverse("renouveler", args=[self.m.token])
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        self.assertEqual(Paiement.objects.count(), 0)

    def test_visiteur_ne_peut_pas_valider(self):
        p = services.demander_renouvellement(self.m, self.forfait, "caisse")
        r = self.client.post(reverse("paiement_traiter", args=[p.pk, "valider"]))
        self.assertEqual(r.status_code, 302)  # redirigé vers la connexion
        p.refresh_from_db()
        self.assertEqual(p.statut, "attente")

    @override_settings(PAIEMENT_MOBILE_ACTIF=False)
    def test_caisse_uniquement_tant_que_mobile_inactif(self):
        url = reverse("renouveler", args=[self.m.token])
        page = self.client.get(url)
        self.assertContains(page, "Caisse")
        self.assertNotContains(page, 'value="orange"')
        self.assertNotContains(page, 'value="momo"')
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "orange", "reference": "OM1"})
        self.assertEqual(Paiement.objects.count(), 0)
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        self.assertEqual(Paiement.objects.get().mode, "caisse")


class CaisseTests(AtelierTests):
    def setUp(self):
        super().setUp()
        self.resp2 = User.objects.create_user("resp2", password="x", first_name="Second")
        Profil.objects.create(user=self.resp2)
        m2 = Membre.objects.create(nom="Bako Ali", telephone="6", cree_par=self.resp2)
        services.ajouter_forfait(m2, Forfait.objects.create(nom="5 h", heures=Decimal("5"), prix=3000), self.resp2)

    def test_admin_voit_tout_et_responsable_seulement_le_sien(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("caisse"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["periodes"][0][2]["total"], 8000)
        self.assertEqual({x["nom"] for x in r.context["par_responsable"]}, {"Resp", "Second"})
        self.client.force_login(self.resp)
        r = self.client.get(reverse("caisse"))
        self.assertEqual(r.context["periodes"][0][2]["total"], 5000)
        self.assertEqual(r.context["par_responsable"], [])

    def test_export_csv_reserve_a_l_admin_et_date_invalide(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("caisse") + "?export=csv")
        self.assertEqual(r["Content-Type"].split(";")[0], "text/csv")
        self.assertIn("Awa Bello", r.content.decode("utf-8"))
        self.assertEqual(self.client.get(reverse("caisse") + "?date=nimporte").status_code, 200)
        self.client.force_login(self.resp)
        self.assertNotEqual(self.client.get(reverse("caisse") + "?export=csv")["Content-Type"].split(";")[0], "text/csv")

    def test_jour_passe_vide(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("caisse") + "?date=2020-01-15")
        self.assertEqual(r.context["periodes"][0][2]["total"], 0)
