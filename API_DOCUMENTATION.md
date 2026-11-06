# Documentation de l'API — ProfileLink

> **Statut : implémenté et testé.** Mise à jour : 2026-11-06.

## Conventions

- **Hôte :** `https://api.profil.mg`, préfixe `/api/v1`. Exceptions : `/r/{username}` et `/health`.
- **Format :** JSON en UTF-8, dates ISO 8601 en UTC.
- **Username :** insensible à la casse, normalisé en minuscules.
- **Authentification :** cookie `pl_session` (`HttpOnly; Secure; SameSite=Lax; Domain=profil.mg`), réservé à l'administrateur.
- **CORS :** origine `https://profil.mg` uniquement, avec `credentials`.
- **CSRF :** toute méthode non-GET sur `/auth/*` et `/admin/*` doit venir du site ou de la même origine que l'API (Swagger), sinon `403 origin_not_allowed`.

### Erreurs

Format FastAPI standard. `detail` est un code stable, traduit en français par le frontend.

```json
{ "detail": "invalid_destination" }
```

Les erreurs de validation Pydantic gardent le format `422` natif.

| Statut | Code | Cas |
|---|---|---|
| 401 | `not_authenticated` | Cookie absent, invalide ou expiré |
| 401 | `invalid_credentials` | Email ou mot de passe incorrect, sans distinction |
| 403 | `origin_not_allowed` | `Origin` refusée |
| 403 | `invalid_registration_code` | Code d'inscription incorrect |
| 404 | `not_found` | Ressource absente |
| 409 | `email_taken` | Compte administrateur existant |
| 413 | `file_too_large` | Image de plus de 5 Mo |
| 415 | `unsupported_image` | Format refusé ou fichier illisible |
| 422 | `invalid_destination`, `invalid_instagram`, `invalid_range` | Validation métier |
| 429 | — | Rate limiting Nginx |

## Redirection

### `GET /r/{username}`

Public, sans authentification. Paramètre optionnel `ref`, domaine d'origine envoyé par la page.

| Situation | Réponse | Clic compté |
|---|---|---|
| VA et lien actifs | `302`, `Location: <destination>` | Oui |
| VA absent ou inactif | `302`, `Location: https://profil.mg/{username}` | Non |
| Lien inactif | `302`, `Location: https://profil.mg/{username}` | Non |
| Username de format invalide | `404` | Non |

```http
GET /r/bryan HTTP/1.1
Host: api.profil.mg

HTTP/1.1 302 Found
Location: https://example.com/external-page
Cache-Control: no-store
X-Robots-Tag: noindex, nofollow
```

- La destination vient **toujours** de PostgreSQL. Aucun paramètre de requête ne peut l'influencer.
- `ref` est seulement stocké, après validation comme nom d'hôte.
- La destination devient visible dans `Location` au moment de la redirection : aucun secret n'est promis après le clic.
- Le `robots.txt` de `api.profil.mg` exclut `/r/` et `/api/`, pas `/media/` : les robots doivent pouvoir lire `og:image`.

## Pages publiques

### `GET /api/v1/public/profiles/{username}`

Public. Réponse `200` pour un VA actif :

```json
{
  "id": "0b7e9a3e-1f55-4b7a-9d7e-3c1f9e2a4d10",
  "username": "bryan",
  "first_name": "Bryan",
  "last_name": "Rakoto",
  "age": 27,
  "photo_url": "https://api.profil.mg/media/6f1c2a.webp",
  "is_active": true,
  "link_available": true
}
```

`link_available` indique si le bouton doit s'afficher.

Pour un VA désactivé, la réponse reste `200` et n'expose rien de personnel :

```json
{
  "id": "0b7e9a3e-1f55-4b7a-9d7e-3c1f9e2a4d10",
  "username": "bryan",
  "first_name": null,
  "last_name": null,
  "age": null,
  "photo_url": null,
  "is_active": false,
  "link_available": false
}
```

Username inconnu : `404`.

**Ne contient jamais** `destination_url`, `instagram_url` ni l'identifiant du lien. Le schéma de réponse Pydantic est une liste blanche, et un test parcourt toutes les routes publiques pour le vérifier.

### `POST /api/v1/public/profiles/{username}/visit`

Public, envoyé par `navigator.sendBeacon`, sans corps. Paramètre optionnel `ref`.

Réponse : `204`, y compris pour un VA inconnu. Seul un VA actif génère un enregistrement.

## Authentification administrateur

Il n'existe **aucune inscription publique**. Un compte se crée de deux façons.

**Sur le serveur :**

```bash
docker compose exec backend python -m app.cli create-admin admin@example.com
```

Le mot de passe, 12 caractères au minimum, est demandé de façon interactive et jamais passé en argument. `reset-password` fonctionne de la même façon et ferme toutes les sessions du compte.

**Par `POST /api/v1/auth/register` :** visible dans Swagger (`/docs`) en développement, section `auth`.

```json
{
  "email": "admin@example.com",
  "password": "un-mot-de-passe-long",
  "password_confirm": "un-mot-de-passe-long",
  "registration_code": "<REGISTRATION_TOKEN>"
}
```

**Par la page `https://api.profil.mg/register` :** le même formulaire en HTML, servi par FastAPI. Elle sert en production, où `/docs` est désactivé.

Aucune de ces deux voies n'apparaît dans le frontend, et aucune n'ouvre de session.

| Situation | Réponse |
|---|---|
| `REGISTRATION_TOKEN` non configuré | `404` sur `GET` et `POST` |
| Code incorrect | `403 invalid_registration_code` |
| Saisie invalide | `422` |
| Compte existant | `409 email_taken` (`422` sur la page HTML) |
| Compte créé | `201` |

### `POST /api/v1/auth/login`

```json
{ "email": "admin@example.com", "password": "un-mot-de-passe-long" }
```

- `200`, cookie posé. Corps identique à `GET /auth/me`.
- `401 invalid_credentials`. Un hachage factice est calculé pour un email inconnu, afin que le temps de réponse ne révèle pas son existence.

### `POST /api/v1/auth/logout`

Authentifié. `204`, session supprimée en base et cookie effacé.

### `POST /api/v1/auth/refresh`

Authentifié. Remplace le jeton et repousse l'expiration à 14 jours.

### `GET /api/v1/auth/me`

Authentifié.

```json
{
  "id": "7a4e1c7c-9a58-4d6f-8d90-5f3e0a4c1b22",
  "email": "admin@example.com",
  "session_expires_at": "2026-11-20T09:00:00Z"
}
```

## Gestion des VA

Tous les endpoints `/admin/*` exigent une session administrateur valide. Chaque modification invalide le cache de la page publique concernée.

### Objet VA

```json
{
  "id": "0b7e9a3e-1f55-4b7a-9d7e-3c1f9e2a4d10",
  "username": "bryan",
  "first_name": "Bryan",
  "last_name": "Rakoto",
  "age": 27,
  "instagram_url": "https://www.instagram.com/bryan.rakoto",
  "photo_url": "https://api.profil.mg/media/6f1c2a.webp",
  "is_active": true,
  "public_url": "https://profil.mg/bryan",
  "link": {
    "destination_url": "https://example.com/external-page",
    "is_active": true
  },
  "created_at": "2026-11-06T09:00:00Z",
  "updated_at": "2026-11-06T09:00:00Z"
}
```

### Routes

| Méthode | Route | Corps | Succès |
|---|---|---|---|
| `GET` | `/api/v1/admin/vas` | — | `200`, tableau de VA |
| `POST` | `/api/v1/admin/vas` | multipart, voir ci-dessous | `201`, VA |
| `GET` | `/api/v1/admin/vas/{va_id}` | — | `200`, VA |
| `PUT` | `/api/v1/admin/vas/{va_id}` | `first_name`, `last_name`, `age`, `instagram_url` | `200`, VA |
| `DELETE` | `/api/v1/admin/vas/{va_id}` | — | `204` |
| `POST` | `/api/v1/admin/vas/{va_id}/photo` | multipart, champ `file` | `200`, VA |
| `PATCH` | `/api/v1/admin/vas/{va_id}/status` | `{ "is_active": false }` | `200`, VA |
| `PUT` | `/api/v1/admin/vas/{va_id}/link` | `{ "destination_url": "…" }` | `200`, VA |
| `PATCH` | `/api/v1/admin/vas/{va_id}/link/status` | `{ "is_active": false }` | `200`, VA |

### `POST /api/v1/admin/vas`

`multipart/form-data`. Tous les champs sont obligatoires. Un échec ne laisse ni profil ni fichier.

| Champ | Règle |
|---|---|
| `first_name`, `last_name` | 1 à 100 caractères |
| `age` | Entier de 1 à 120 |
| `instagram_url` | Lien vers `instagram.com` ou `www.instagram.com`, avec un chemin |
| `destination_url` | Voir [Validation des destinations](#validation-des-destinations) |
| `photo` | JPEG, PNG ou WebP, 5 Mo au plus |

Le profil et son lien sont créés dans une seule transaction, et l'URL publique est générée automatiquement :

| Prénom, nom | URL | Cas |
|---|---|---|
| Bryan Rakoto | `/bryan` | Nominal |
| Bryan Rabe | `/bryan-rabe` | `bryan` est pris |
| Bryan Rakoto | `/bryan-rakoto-2` | Homonyme complet |
| Léa Andrïa | `/lea-andria` | Accents retirés, `lea` déjà pris |
| Jo Rakoto | `/jo-rakoto` | Prénom trop court |
| Admin Rakoto | `/admin-rakoto` | Prénom réservé |

L'URL ne change plus ensuite, même si le nom est corrigé.

### Photos

Le type est déterminé par le décodage de l'image, pas par le `Content-Type` du client. L'image est recadrée en 800×800, réencodée en WebP et débarrassée de ses métadonnées. Remplacer une photo supprime l'ancien fichier.

### Validation des destinations

Appliquée à la création et à la modification. Tout refus répond `422 invalid_destination`.

| Règle | Exemples refusés |
|---|---|
| Schéma `http` ou `https` | `javascript:`, `data:`, `file:`, `ftp:` |
| URL bien formée, 2 048 caractères au plus | Hôte vide, caractères de contrôle, espaces, `\` |
| Pas d'identifiants dans l'URL | `https://paypal.com@evil.test/` |
| Pas de nom local | `localhost`, `*.localhost`, `*.local`, `*.internal`, nom sans point |
| Pas d'IP non publique, sous toutes ses formes | `127.0.0.1`, `10.x`, `192.168.x`, `169.254.169.254`, `[::1]`, `[::ffff:127.0.0.1]`, `2130706433`, `0x7f.1` |
| Pas de boucle vers le service | `profil.mg`, `*.profil.mg` |
| Le domaine se résout, et uniquement vers des IP publiques | Domaine inexistant, domaine pointant vers `10.0.0.5` |

Les noms de domaine sont normalisés en punycode. L'API ne contacte jamais la destination elle-même.

## Statistiques

Fuseau `Indian/Antananarivo`. Aucune réponse ne contient `ip_hash`. Toutes les routes acceptent un `va_id` optionnel : sans lui, les chiffres couvrent tous les VA.

### `GET /api/v1/admin/analytics/overview`

```json
{
  "total_visits": 1240,
  "total_clicks": 372,
  "conversion_rate": 0.3,
  "va_count": 12,
  "active_va_count": 11,
  "recent_activity": [
    {
      "type": "click",
      "va_username": "bryan",
      "occurred_at": "2026-11-06T08:58:00Z",
      "referer_domain": "l.instagram.com"
    }
  ]
}
```

`conversion_rate` vaut `null` s'il n'y a aucune visite. Il peut dépasser 1 : la valeur n'est pas corrigée.

### `GET /api/v1/admin/analytics/clicks`

| Paramètre | Valeurs | Défaut |
|---|---|---|
| `va_id` | UUID | Tous les VA |
| `granularity` | `day`, `week`, `month` | `day` |
| `from`, `to` | Date `YYYY-MM-DD` | 30 derniers jours |
| `limit`, `offset` | Pagination de l'historique, `limit` ≤ 100 | `50`, `0` |

```json
{
  "granularity": "day",
  "timezone": "Indian/Antananarivo",
  "total": 42,
  "series": [{ "bucket": "2026-11-05", "count": 12 }],
  "history": [
    {
      "va_username": "bryan",
      "clicked_at": "2026-11-06T08:58:00Z",
      "referer_domain": "l.instagram.com",
      "user_agent": "Mozilla/5.0 …"
    }
  ]
}
```

Les périodes sans événement sont renvoyées avec `count: 0`.

### `GET /api/v1/admin/analytics/visits`

Mêmes paramètres `va_id`, `granularity`, `from` et `to`, même réponse sans `history`.

## Service

### `GET /health`

Exécute `SELECT 1`. `200 {"status":"ok"}` ou `503`. Réservé aux healthchecks Docker, non exposé par Nginx.

### Route interne `POST /api/revalidate` (Next.js)

Appelée par FastAPI sur le réseau Docker, avec l'en-tête `X-Revalidate-Secret`. Nginx bloque `/api/` sur `profil.mg`.

```json
{ "usernames": ["bryan"] }
```

## Rate limiting

Appliqué par Nginx, par IP réelle du visiteur.

| Zone | Limite | Rafale |
|---|---|---|
| `/api/v1/auth/*`, `/register` | 20/min, zone partagée | 10 |
| `/api/v1/admin/*` | 120/min | 40 |
| `/r/*`, `/api/v1/public/*`, pages | 300/min | 100 |
