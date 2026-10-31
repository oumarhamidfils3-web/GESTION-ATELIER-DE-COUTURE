# Mise en ligne sur Render

## 1. Envoyer les fichiers sur GitHub
Décompressez `atelier_app.zip` sur l'ordinateur. Ouvrez le dossier **atelier_app** décompressé, puis glissez **son contenu**
(les dossiers `atelier` et `gestion`, et les fichiers `manage.py`, `requirements.txt`, `build.sh`, `README.md`, `.gitignore`)
dans la page « Upload files » du dépôt, puis « Commit changes ».
- N'envoyez pas le fichier .zip lui-même : GitHub ne le décompresse pas.
- `manage.py` et `requirements.txt` doivent apparaître à la **racine** du dépôt (pas dans un sous-dossier).

## 2. Réglages du service Render (onglet Settings)
| Réglage | Valeur |
|---|---|
| Build Command | `bash build.sh` |
| Start Command | `gunicorn atelier.wsgi:application --workers 1 --threads 4 --bind 0.0.0.0:$PORT` |

## 3. Variables d'environnement (onglet Environment)
| Nom | Valeur |
|---|---|
| `SECRET_KEY` | une longue suite de caractères au hasard (50 ou plus) |
| `DEBUG` | `0` |
| `ADMIN_USERNAME` | l'identifiant de l'administrateur |
| `ADMIN_PASSWORD` | son mot de passe (solide) |
| `ADMIN_NOM` | son nom affiché (facultatif) |
| `ALERTES_AUTO` | `1` (le service envoie lui-même les alertes) |
| `DATABASE_URL` | l'adresse interne de la base PostgreSQL Render (voir ci-dessous) |
| `ATELIER_NOM` | le nom de l'atelier |
| `ADMIN_TELEPHONES` | numéros de l'administrateur pour les alertes, séparés par des virgules |
Pour l'envoi réel des SMS et WhatsApp, ajoutez ensuite `NOTIF_BACKEND=twilio` et les variables `TWILIO_...` (voir README).

## 4. Base de données
Sans `DATABASE_URL`, l'application utilise un fichier SQLite qui est **effacé à chaque redémarrage** sur Render :
acceptable seulement pour un essai de quelques minutes. Créez donc une base : New → PostgreSQL, puis copiez son
« Internal Database URL » dans `DATABASE_URL`.
- Formule gratuite : la base expire 30 jours après sa création (essais uniquement).
- Pour la vraie ouverture : service web et base en formule payante, sinon le service s'endort après 15 minutes
  sans visite (les alertes ne partent plus) et les données risquent d'être perdues.

## 5. Lancer
Manual Deploy → « Clear build cache & deploy ». Quand le statut passe à « Live », ouvrez l'adresse du service.
Connectez-vous avec `ADMIN_USERNAME`, créez les forfaits dans `/admin/`, puis les responsables dans `/responsables/`.
`SITE_URL` se règle seule d'après l'adresse Render. **Imprimez les cartes seulement après la mise en service définitive.**

## Si le déploiement échoue
Ouvrez l'onglet Logs du déploiement en échec et envoyez les dernières lignes : elles disent exactement ce qui manque.
