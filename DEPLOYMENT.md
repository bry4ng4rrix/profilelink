# Déploiement — ProfileLink

Déploiement sur un VPS Ubuntu avec Docker Compose et Cloudflare.

**Avant de commencer :** si le VPS héberge déjà des services sur les ports 80 ou 443, ce guide ne s'applique pas tel quel. Le service `nginx` entrerait en conflit avec eux.

## 1. Prérequis

- Ubuntu avec Docker Engine et le plugin Compose.
- `profil.mg` délégué à Cloudflare.
- Enregistrements DNS proxifiés vers le VPS : `profil.mg`, `www.profil.mg`, `api.profil.mg`.

## 2. Pare-feu et SSH

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH
sudo ufw enable
```

Dans `/etc/ssh/sshd_config` : `PasswordAuthentication no` et `PermitRootLogin no`, puis `sudo systemctl reload ssh`.

Testez une nouvelle connexion SSH par clé **avant** de fermer votre session.

Docker publie les ports 80 et 443 en contournant UFW : c'est le certificat client de l'étape 4 qui réserve l'origine à Cloudflare.

## 3. Configuration

```bash
git clone <dépôt> profilelink && cd profilelink
cp .env.example .env
chmod 600 .env
```

Remplacez chaque valeur `<...>` de `.env`. Le mot de passe PostgreSQL doit rester hexadécimal, car il entre dans une URL.

## 4. Cloudflare et certificats

Dans le tableau de bord Cloudflare :

1. **SSL/TLS :** mode **Full (strict)**.
2. **Origin Server :** créez un certificat pour `profil.mg` et `*.profil.mg`.
3. **Authenticated Origin Pulls :** activez-les pour la zone.
4. **Cache Rules :** contournez le cache pour `api.profil.mg/r/*` et `api.profil.mg/api/*`.
5. N'activez **aucune** règle « Cache Everything » sur le HTML.

Déposez dans `nginx/certs/`, qui est ignoré par git :

| Fichier | Contenu |
|---|---|
| `origin.pem` | Certificat d'origine |
| `origin.key` | Clé privée, `chmod 600` |
| `cloudflare-origin-pull.pem` | CA des Authenticated Origin Pulls, fournie par Cloudflare |

## 5. Démarrage

```bash
docker compose up -d --build --wait
docker compose ps
```

Les migrations s'exécutent au démarrage du backend. Créez ensuite l'administrateur :

```bash
docker compose exec backend python -m app.cli create-admin admin@profil.mg
```

Pour créer un compte depuis un navigateur :

1. Mettez un code dans `.env` : `REGISTRATION_TOKEN=$(openssl rand -hex 32)`.
2. Appliquez-le : `docker compose up -d backend`.
3. Ouvrez `https://api.profil.mg/register` et créez le compte.
4. **Videz `REGISTRATION_TOKEN`** et relancez la commande de l'étape 2 : la page répond de nouveau 404.

## 6. Vérifications

- `https://profil.mg` mène à la connexion.
- Une page de VA s'affiche, et son bouton redirige.
- `https://profil.mg/api/revalidate` répond 404.
- `curl -k https://<IP-du-VPS>` échoue : l'origine refuse tout sauf Cloudflare.
- PostgreSQL est inaccessible depuis l'extérieur.
- Le [débogueur de partage de Meta](https://developers.facebook.com/tools/debug/) affiche le bon aperçu.

## 7. Sauvegardes

```bash
scripts/backup.sh
```

Le script écrit la base et les photos dans `backups/` et garde 14 jours. **Une sauvegarde restée sur le VPS ne protège pas d'une panne du VPS :** copiez `backups/` ailleurs.

Tâche quotidienne, avec `crontab -e` :

```cron
30 2 * * * cd /chemin/vers/profilelink && scripts/backup.sh >> backups/backup.log 2>&1
```

### Restauration

À tester régulièrement, sur une base vide :

```bash
docker compose exec -T postgres pg_restore -U profilelink -d profilelink --clean --if-exists --no-owner < backups/db-XXXX.dump
docker compose exec -T backend tar -C /app/media -xzf - < backups/media-XXXX.tar.gz
```

## 8. Mises à jour

```bash
scripts/backup.sh
git pull
docker compose up -d --build --wait
```

`BACKEND_URL` et `NEXT_PUBLIC_SITE_URL` étant compilées dans le frontend, changer `FRONTEND_ORIGIN` impose un `--build`.

## 9. Opérations courantes

```bash
# Mot de passe oublié : le remplace et ferme toutes les sessions
docker compose exec backend python -m app.cli reset-password admin@profil.mg

# Journaux
docker compose logs -f backend nginx

# Actualiser les plages Cloudflare, puis recharger Nginx
scripts/update-cloudflare-ips.sh
docker compose exec nginx nginx -s reload
```

## Mode test sur un VPS partagé

`docker-compose.vps.yml` lance FastAPI et PostgreSQL seuls, sans Nginx, sur le port 2560. Il convient à un VPS qui héberge déjà d'autres sites, car il ne touche pas aux ports 80 et 443.

```bash
cd ~/profilelink
docker compose -f docker-compose.vps.yml up -d --build --wait
```

Le `.env` du VPS doit contenir `ENVIRONMENT=development`, `API_PUBLIC_URL=http://<IP>:2560`, `POSTGRES_USER`, `POSTGRES_DB` et `POSTGRES_PASSWORD`, sans `DATABASE_URL`.

**Réservé aux tests.** Ce mode n'a pas de HTTPS, ni de rate limiting, et Swagger y est public. Un visiteur peut aussi fausser l'IP enregistrée dans les statistiques. Laissez `REGISTRATION_TOKEN` vide dès que les comptes sont créés, puis relancez la commande ci-dessus.

## Frontend sur Vercel

Importez le dépôt `frontend_profilelink`. L'adresse de l'API est `BACKEND_URL`, avec le VPS de test pour valeur par défaut dans `frontend/lib/site.ts`.

Le navigateur passe par `/backend` sur Vercel, qui transmet à l'API : tout reste en HTTPS pour lui, même si l'API est en HTTP.

Dans Vercel, ajoutez `REVALIDATE_SECRET`, identique à celui du VPS. Sans lui, une modification met jusqu'à 5 minutes à apparaître.

Dans le `.env` du VPS, avec votre adresse Vercel :

```bash
FRONTEND_ORIGIN=https://<projet>.vercel.app
FRONTEND_INTERNAL_URL=https://<projet>.vercel.app
API_PUBLIC_URL=https://<projet>.vercel.app/backend
```

Relancez ensuite le backend. Tant que `FRONTEND_ORIGIN` ne correspond pas, la connexion est refusée (`origin_not_allowed`).
