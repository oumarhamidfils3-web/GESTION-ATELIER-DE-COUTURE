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

    def connecter_membre(self, m=None):
        m = m or self.m
        sess = self.client.session
        sess["membre_id"] = m.pk
        sess.save()

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

    def test_scan_carte_par_un_membre_demande_le_code(self):
        r = self.client.get(reverse("scan", args=[self.m.token]))
        self.assertRedirects(r, reverse("membre_acces", args=[self.m.token]))
        self.assertEqual(self.client.get(reverse("espace")).status_code, 302)  # pas de session : refusé

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
        self.assertNotEqual(self.client.get(reverse("membres")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("accueil")), "Dans l")

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

from .models import Alerte, Demande, Envoi, Paiement  # noqa: E402


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
        self.connecter_membre(); url = reverse("espace_renouveler")
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
        self.connecter_membre(); url = reverse("espace_renouveler")
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
        self.connecter_membre(); url = reverse("espace_renouveler")
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        self.assertEqual(Paiement.objects.filter(statut="attente").count(), 1)
        self.assertEqual(Paiement.objects.filter(statut="annule").count(), 1)

    def test_renouvellement_membre_epuise_reactive_acces(self):
        s = services.valider_entree(self.m, self.resp)
        s.entree_at = timezone.now() - timedelta(hours=11)
        s.save()
        services.cloturer_depassements()
        self.connecter_membre(); url = reverse("espace_renouveler")
        self.client.post(url, {"forfait": self.forfait.pk, "mode": "caisse"})
        p = Paiement.objects.get()
        services.valider_paiement(p, self.resp)
        services.valider_entree(self.m, self.resp)  # l'accès est rétabli

    def test_membre_revoque_ne_peut_pas_renouveler(self):
        services.revoquer(self.m, self.admin, "x")
        self.connecter_membre(); url = reverse("espace_renouveler")
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
        self.connecter_membre(); url = reverse("espace_renouveler")
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


import io  # noqa: E402

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from PIL import Image  # noqa: E402


class PhotoTests(AtelierTests):
    def _image(self):
        buf = io.BytesIO()
        Image.new("RGB", (1200, 1600), "navy").save(buf, "PNG")
        return SimpleUploadedFile("moi.png", buf.getvalue(), content_type="image/png")

    def test_photo_reduite_stockee_en_base_et_servie_aux_responsables(self):
        self.client.force_login(self.resp)
        r = self.client.post(reverse("membre_nouveau"), {
            "nom": "Photo Test", "telephone": "670", "forfait": self.forfait.pk, "photo": self._image()})
        self.assertEqual(r.status_code, 302)
        m = Membre.objects.get(nom="Photo Test")
        self.assertTrue(m.photo_data)
        img = Image.open(io.BytesIO(bytes(m.photo_data)))
        self.assertLessEqual(max(img.size), 500)
        rep = self.client.get(reverse("photo_membre", args=[m.pk]))
        self.assertEqual(rep["Content-Type"], "image/jpeg")
        self.assertContains(self.client.get(reverse("membre_detail", args=[m.pk])), "/photo/")
        for nom in ("fiche_pdf", "carte_pdf"):
            self.assertTrue(self.client.get(reverse(nom, args=[m.pk])).content.startswith(b"%PDF"))
        self.client.logout()
        self.assertEqual(self.client.get(reverse("photo_membre", args=[m.pk])).status_code, 302)  # photo privée

    def test_photo_absente_donne_404(self):
        self.client.force_login(self.resp)
        self.assertEqual(self.client.get(reverse("photo_membre", args=[self.m.pk])).status_code, 404)


class EspaceMembreTests(AtelierTests):
    def setUp(self):
        super().setUp()
        self.m.definir_pin("4821")
        self.m.save()
        self.autre = Membre.objects.create(nom="Autre Membre", telephone="671", cree_par=self.resp)
        self.autre.definir_pin("1111")
        self.autre.save()
        services.ajouter_forfait(self.autre, self.forfait, self.resp)

    def test_connexion_par_numero_et_code(self):
        r = self.client.post(reverse("atelier_acces"), {"numero": self.m.numero, "code": "4821"})
        self.assertRedirects(r, reverse("espace"))
        page = self.client.get(reverse("espace"))
        for libelle in ("Entrée de l'atelier", "Sortie de l'atelier", "Renouveler mon forfait", "Consulter mon forfait"):
            self.assertContains(page, libelle)

    def test_numero_souple_et_mauvais_code(self):
        r = self.client.post(reverse("atelier_acces"), {"numero": "at 1", "code": "0000"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "incorrect")
        self.assertEqual(self.client.get(reverse("espace")).status_code, 302)
        r = self.client.post(reverse("atelier_acces"), {"numero": str(self.m.pk), "code": "4821"})
        self.assertRedirects(r, reverse("espace"))

    def test_blocage_apres_cinq_erreurs(self):
        for _ in range(5):
            self.client.post(reverse("atelier_acces"), {"numero": self.m.numero, "code": "0000"})
        r = self.client.post(reverse("atelier_acces"), {"numero": self.m.numero, "code": "4821"})
        self.assertContains(r, "Trop d")
        self.assertEqual(self.client.get(reverse("espace")).status_code, 302)

    def test_acces_par_la_carte(self):
        url = reverse("membre_acces", args=[self.m.token]) + "?suite=renouveler"
        self.assertContains(self.client.get(url), self.m.numero)
        r = self.client.post(url, {"code": "4821"})
        self.assertRedirects(r, reverse("espace_renouveler"))

    def test_le_membre_ne_voit_que_son_compte(self):
        self.connecter_membre()
        page = self.client.get(reverse("espace"))
        self.assertContains(page, "Awa Bello")
        self.assertNotContains(page, "Autre Membre")
        self.assertNotContains(self.client.get(reverse("espace_forfait")), "Autre Membre")
        # aucune page responsable
        for nom in ("membres", "caisse", "responsables", "affiche_pdf"):
            self.assertIn(self.client.get(reverse(nom)).status_code, (302, 403))
        self.assertRedirects(self.client.get(reverse("accueil")), reverse("espace"))
        for nom, args in (("membre_detail", [self.autre.pk]), ("fiche_pdf", [self.autre.pk]), ("photo_membre", [self.autre.pk])):
            self.assertEqual(self.client.get(reverse(nom, args=args)).status_code, 302)
        self.assertEqual(self.client.post(reverse("valider", args=[self.autre.pk])).status_code, 302)
        self.assertIsNone(self.autre.seance_ouverte())

    def test_le_membre_ne_peut_pas_valider_sa_propre_entree(self):
        self.connecter_membre()
        self.client.post(reverse("espace_entree"))
        self.assertIsNone(self.m.seance_ouverte())  # rien ne démarre sans un responsable
        d = self.m.demande_en_attente()
        self.assertEqual(d.type, "entree")
        self.assertContains(self.client.get(reverse("espace")), "en attente")
        r = self.client.post(reverse("demande_traiter", args=[d.pk, "valider"]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Demande.objects.get(pk=d.pk).statut, "attente")

    def test_entree_puis_sortie_validees_par_un_responsable(self):
        self.connecter_membre()
        self.client.post(reverse("espace_entree"))
        d = self.m.demande_en_attente()
        services.traiter_demande(d, self.resp, True)
        s = self.m.seance_ouverte()
        self.assertIsNotNone(s)
        self.assertEqual(s.entree_par, self.resp)
        s.entree_at = timezone.now() - timedelta(hours=2)
        s.save()
        self.client.post(reverse("espace_sortie"))
        d2 = self.m.demande_en_attente()
        self.assertEqual(d2.type, "sortie")
        # le responsable valide plus tard : le temps s'arrête à l'heure du scan du membre
        Demande.objects.filter(pk=d2.pk).update(cree_le=timezone.now() - timedelta(minutes=30))
        services.traiter_demande(Demande.objects.get(pk=d2.pk), self.resp, True)
        self.assertIsNone(self.m.seance_ouverte())
        ab = self.m.abonnement_actif()
        self.assertAlmostEqual(ab.consomme_s, 5400, delta=5)  # 1 h 30 min, pas 2 h

    def test_refus_et_annulation(self):
        self.connecter_membre()
        self.client.post(reverse("espace_entree"))
        services.traiter_demande(self.m.demande_en_attente(), self.resp, False)
        self.assertIsNone(self.m.seance_ouverte())
        self.client.post(reverse("espace_entree"))
        self.client.post(reverse("espace_annuler"))
        self.assertIsNone(self.m.demande_en_attente())
        self.assertEqual(self.m.demandes.filter(statut="annulee").count(), 1)

    def test_regles_des_demandes(self):
        self.connecter_membre()
        self.client.post(reverse("espace_sortie"))  # pas dans l'atelier
        self.assertEqual(Demande.objects.count(), 0)
        self.client.post(reverse("espace_entree"))
        self.client.post(reverse("espace_entree"))  # déjà en attente
        self.assertEqual(Demande.objects.count(), 1)

    def test_validation_directe_solde_la_demande(self):
        self.connecter_membre()
        self.client.post(reverse("espace_entree"))
        services.valider_entree(self.m, self.resp)
        self.assertIsNone(self.m.demande_en_attente())

    def test_membre_epuise_ou_revoque_ne_peut_pas_demander_entree(self):
        services.revoquer(self.m, self.admin, "x")
        self.connecter_membre()
        r = self.client.post(reverse("espace_entree"), follow=True)
        self.assertContains(r, "révoqué")
        self.assertEqual(Demande.objects.count(), 0)

    def test_pin_affiche_a_l_inscription_et_reinitialisable(self):
        self.client.force_login(self.resp)
        r = self.client.post(reverse("membre_nouveau"), {
            "nom": "Nouvelle", "telephone": "672", "forfait": self.forfait.pk})
        n = Membre.objects.get(nom="Nouvelle")
        pin = self.client.session[f"pin_{n.pk}"]
        self.assertTrue(n.verifier_pin(pin))
        self.assertNotIn(pin, n.pin_hash)
        self.assertContains(self.client.get(reverse("membre_detail", args=[n.pk])), pin)
        self.assertTrue(self.client.get(reverse("fiche_pdf", args=[n.pk])).content.startswith(b"%PDF"))
        self.client.post(reverse("membre_pin_masquer", args=[n.pk]))
        self.assertNotContains(self.client.get(reverse("membre_detail", args=[n.pk])), "Mot de passe provisoire du membre")
        self.client.post(reverse("membre_pin", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.verifier_pin(self.client.session[f"pin_{n.pk}"]))

    def test_accueil_responsable_liste_les_demandes_et_affiche(self):
        self.connecter_membre()
        self.client.post(reverse("espace_entree"))
        self.client.force_login(self.resp)
        page = self.client.get(reverse("accueil"))
        self.assertContains(page, "Demandes des membres")
        self.assertContains(page, "Awa Bello")
        self.assertTrue(self.client.get(reverse("affiche_pdf")).content.startswith(b"%PDF"))

    def test_responsable_connecte_sur_l_affiche_va_a_l_accueil(self):
        self.client.force_login(self.resp)
        self.assertRedirects(self.client.get(reverse("atelier_acces")), reverse("accueil"))

    def test_quitter_la_session(self):
        self.connecter_membre()
        self.client.post(reverse("espace_quitter"))
        self.assertEqual(self.client.get(reverse("espace")).status_code, 302)


class AccesEtMotDePasseTests(EspaceMembreTests):
    def test_ni_responsable_ni_membre_dans_l_administration(self):
        self.client.force_login(self.resp)
        for url in ("/admin/", "/admin/gestion/membre/", "/admin/auth/user/"):
            r = self.client.get(url)
            self.assertIn(r.status_code, (302, 403))
            if r.status_code == 302:
                self.assertIn("/admin/login/", r["Location"])
        self.client.logout()
        self.connecter_membre()
        r = self.client.get("/admin/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login/", r["Location"])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_lien_administration_reserve_a_l_administrateur(self):
        self.client.force_login(self.resp)
        page = self.client.get(reverse("accueil"))
        self.assertNotContains(page, "Administration")
        self.assertNotContains(page, ">Responsables<")
        self.client.force_login(self.admin)
        page = self.client.get(reverse("accueil"))
        self.assertContains(page, "Administration")
        self.assertContains(page, "Responsables")

    def test_un_responsable_ne_peut_pas_ajouter_un_responsable(self):
        self.client.force_login(self.resp)
        avant = User.objects.count()
        r = self.client.post(reverse("responsables"), {
            "identifiant": "pirate", "nom_complet": "Pirate", "mot_de_passe": "secret123"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(User.objects.count(), avant)
        self.assertEqual(self.client.post(reverse("responsable_basculer", args=[self.resp.profil.pk])).status_code, 403)

    def test_un_membre_ne_peut_pas_inscrire_un_membre(self):
        self.connecter_membre()
        avant = Membre.objects.count()
        self.assertEqual(self.client.get(reverse("membre_nouveau")).status_code, 302)
        r = self.client.post(reverse("membre_nouveau"), {
            "nom": "Intrus", "telephone": "1", "forfait": self.forfait.pk})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/connexion/", r["Location"])
        self.assertEqual(Membre.objects.count(), avant)

    def test_menu_du_membre_ne_contient_que_accueil(self):
        self.connecter_membre()
        page = self.client.get(reverse("espace"))
        self.assertContains(page, "<a href=\"%s\">Accueil</a>" % reverse("espace"))
        for interdit in ("Inscrire", "Caisse", "Membres</a>", "Responsables", "Administration", "Déconnexion</button>"):
            self.assertNotContains(page, interdit)

    def test_page_de_choix_pour_un_visiteur(self):
        page = self.client.get(reverse("accueil"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Je suis membre")
        self.assertContains(page, "Je suis responsable")
        self.assertNotContains(page, "Inscrire")

    def test_connexion_par_mot_de_passe_sans_qr_code(self):
        self.m.definir_pin("MotDePasse2026")
        self.m.save()
        r = self.client.post(reverse("atelier_acces"), {"numero": self.m.numero, "code": "MotDePasse2026"})
        self.assertRedirects(r, reverse("espace"))

    def test_changer_son_mot_de_passe(self):
        self.connecter_membre()
        url = reverse("espace_mot_de_passe")
        self.assertEqual(self.client.get(url).status_code, 200)
        # actuel faux, trop court, confirmation différente : rien ne change
        for donnees in ({"actuel": "faux", "nouveau": "nouveau123", "confirmation": "nouveau123"},
                        {"actuel": "4821", "nouveau": "abc", "confirmation": "abc"},
                        {"actuel": "4821", "nouveau": "nouveau123", "confirmation": "autre123"}):
            self.client.post(url, donnees)
            self.m.refresh_from_db()
            self.assertTrue(self.m.verifier_pin("4821"))
        r = self.client.post(url, {"actuel": "4821", "nouveau": "nouveau123", "confirmation": "nouveau123"})
        self.assertRedirects(r, reverse("espace"))
        self.m.refresh_from_db()
        self.assertTrue(self.m.verifier_pin("nouveau123"))
        self.assertFalse(self.m.verifier_pin("4821"))
        # connexion avec le nouveau mot de passe depuis un autre téléphone
        self.client.logout()
        r = self.client.post(reverse("atelier_acces"), {"numero": self.m.numero, "code": "nouveau123"})
        self.assertRedirects(r, reverse("espace"))

    def test_changement_de_mot_de_passe_reserve_au_membre_connecte(self):
        self.assertEqual(self.client.get(reverse("espace_mot_de_passe")).status_code, 302)
