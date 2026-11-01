# Atelier de couture — gestion des abonnements (bloc 1)

## Démarrage
```
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser      # c'est l'administrateur
SITE_URL=https://votre-adresse ATELIER_NOM="Nom de l'atelier" python manage.py runserver 0.0.0.0:8000
```
1. Connectez-vous sur `/admin/` et créez au moins un forfait (ex. « 10 heures », 10 h, 5000 FCFA).
2. Sur `/responsables/`, l'administrateur crée les comptes des responsables et peut retirer ou rétablir leur accès.
3. Un responsable inscrit un membre (`/membres/nouveau/`) : la fiche d'inscription et la carte de membre sont générées en PDF.

## Important : SITE_URL
Les QR codes contiennent l'adresse définie par `SITE_URL`. Elle doit être joignable depuis les téléphones
(adresse publique ou IP du réseau de l'atelier). Si vous la changez, réimprimez les cartes.

## Accès des membres (téléphone)
- Un **seul QR code**, imprimé sur l'affiche d'entrée (menu de l'accueil → « Affiche du QR code d'entrée »), sert à tous les membres.
- Le membre s'identifie avec son **numéro** (AT-0001) et son **mot de passe** : soit en scannant le QR code, soit directement depuis la page d'accueil du site (« Je suis membre »).
  Le mot de passe provisoire (4 chiffres) est imprimé sur sa fiche d'inscription ; il le change depuis son espace (« Changer mon mot de passe »).
  Après 5 erreurs, son compte est bloqué 15 minutes. Un responsable peut créer un nouveau mot de passe provisoire depuis sa fiche.
- Le menu du membre ne contient que **Accueil**.
- À chaque scan, 4 options : **entrée de l'atelier**, **sortie de l'atelier**, **renouveler mon forfait**, **consulter mon forfait**.
- Il ne voit que son propre compte. Il **ne valide rien lui-même** : son entrée, sa sortie et son paiement sont des demandes que
  le responsable ou l'administrateur valide depuis l'accueil (« Demandes des membres », « Paiements à valider »).
- Entrée : le compteur démarre à la validation. Sortie : il s'arrête à l'heure où le membre a scanné, même si la validation vient plus tard.
- Le QR de la carte reste utilisable : scanné par un responsable connecté, il ouvre l'écran de validation ; scanné par le membre, il demande son code.

## Qui peut faire quoi
- **Administrateur** (seul à entrer dans `/admin/`) : crée et retire les responsables, révoque un abonnement, voit toute la caisse.
- **Responsable** : inscrit les membres, valide entrées, sorties et paiements, voit ses propres encaissements. Il ne peut ni créer un responsable ni entrer dans l'administration.
- **Membre** : voit et gère seulement son propre compte ; il ne peut inscrire personne ni rien valider lui-même.

## Fonctionnement
- Un seul QR par carte. Scanné avec la caméra du téléphone d'un responsable connecté, il ouvre l'écran de validation
  (entrée ou sortie selon l'état du membre). Scanné par le membre, il ouvre son espace (temps restant, séances).
- Sans carte : le responsable valide par le nom depuis la liste des membres (marqué « sans carte »).
- À 0 h : la séance est clôturée à l'heure exacte d'épuisement, l'accès est coupé et l'alerte s'affiche sur l'accueil
  (administrateur et responsable qui a validé l'entrée). Le membre renouvelle sur place.
- L'administrateur révoque un abonnement depuis la fiche du membre.

## Renouvellement et paiement (bloc 2)
**Pour l'instant : caisse uniquement.** Orange Money et Mobile Money sont masqués et refusés par le serveur tant que
`PAIEMENT_MOBILE_ACTIF` n'est pas à `1` (à activer après la signature du contrat mobile).

Le QR de renouvellement (verso de la carte, fiche d'inscription) ouvre une page où le membre choisit :
1. son forfait, 2. son mode de paiement : **Orange Money**, **Mobile Money** ou **Caisse**.
- Orange Money / Mobile Money : le membre envoie le montant au numéro de l'atelier (`ORANGE_MONEY_NUMERO`, `MOMO_NUMERO`) et saisit la référence reçue par SMS.
- Caisse : il règle sur place.
La demande apparaît dans « Paiements à valider » sur l'accueil. **Les heures ne sont ajoutées qu'après validation** par un responsable ou l'administrateur (ou refus).
Un membre révoqué ne peut pas renouveler en ligne.

## Caisse
Menu « Caisse » : recettes du jour, de la semaine et du mois, avec navigation par date. L'administrateur voit tous les
encaissements, le détail par responsable et peut exporter la journée en CSV ; un responsable ne voit que les siens.
Un encaissement est enregistré à l'inscription ou quand un paiement est validé, au nom de celui qui l'a validé.

## Alertes SMS + WhatsApp
Chaque alerte part par les deux canaux : au membre, au responsable qui a validé son entrée, et à l'administrateur.
- **2 h avant la fin** : dès qu'une séance en cours a 2 h ou moins devant elle (une fois par abonnement et par renouvellement).
- **Heures épuisées** : l'accès est coupé et l'alerte part.
À lancer en tâche de fond (toutes les minutes) :
```
python manage.py envoyer_alertes --boucle        # ou : cron "* * * * * python manage.py envoyer_alertes"
```
Variables d'environnement : `NOTIF_BACKEND` (`console` pour essayer, `twilio` pour l'envoi réel), `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_SMS_FROM`, `TWILIO_WHATSAPP_FROM`, `ADMIN_TELEPHONES` (numéros séparés par des virgules),
`PAYS_INDICATIF` (237 par défaut). Les téléphones des responsables se saisissent à leur création ; ceux de l'administrateur
via `ADMIN_TELEPHONES` ou son profil dans `/admin/`. Chaque envoi (réussi ou non) est consigné dans `/admin/` (Envois).
Remarque : WhatsApp impose des modèles de message approuvés pour écrire à un contact hors conversation récente.

## Tests
`python manage.py test`
