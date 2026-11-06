# Documentation de l'API — ProfileLink

> **Statut : contrat proposé, en attente de validation (phase 1).** Rien n'est implémenté à ce stade.
> Les ajouts au brief sont marqués *(ajout)* et justifiés dans [ARCHITECTURE.md](ARCHITECTURE.md#6-écarts-par-rapport-au-brief).

## Conventions

- **Hôte :** `https://api.profil.mg`, préfixe `/api/v1`. Exceptions : `/r/{username}` et `/health`.
- **Format :** JSON en UTF-8, dates ISO 8601 en UTC.
- **Username :** insensible à la casse, normalisé en minuscules.
- **Authentification :** cookie `pl_session` (`HttpOnly; Secure; SameSite=Lax; Domain=profil.mg`).
- **CORS :** origine `https://profil.mg` uniquement, avec `credentials`.
- **CSRF :** toute méthode non-GET sur `/auth/*` et `/owner/*` doit porter une `Origin` autorisée, sinon `403 origin_not_allowed`.

### Erreurs

Format FastAPI standard. `detail` est un code stable, traduit en français par le frontend.

```json
{ "detail": "username_taken" }
```

Les erreurs de validation Pydantic gardent le format `422` natif, avec un tableau `detail`.

| Statut | Code | Cas |
|---|---|---|
| 401 | `not_authenticated` | Cookie absent, invalide ou expiré |
| 401 | `invalid_credentials` | Email ou mot de passe incorrect, sans distinction |
| 403 | `origin_not_allowed` | `Origin` refusée |
| 404 | `not_found` | Ressource absente **ou appartenant à un autre propriétaire** |
| 409 | `email_taken`, `username_taken`, `link_exists` | Conflit |
| 413 | `file_too_large` | Image de plus de 5 Mo |
| 415 | `unsupported_image` | Format refusé ou fichier illisible |
| 422 | `invalid_destination`, `reserved_username` | Validation métier |
| 429 | — | Rate limiting Nginx |

Un accès à la ressource d'un autre propriétaire répond 404 et non 403 : l'API ne confirme pas son existence.

## Redirection

### `GET /r/{username}`

Public, sans authentification. Paramètre optionnel *(ajout)* : `ref`, domaine d'origine envoyé par la page.

| Situation | Réponse | Clic compté |
|---|---|---|
| Profil et lien actifs | `302`, `Location: <destination>` | Oui |
| Profil absent, inactif ou compte suspendu | `302`, `Location: https://profil.mg/{username}` | Non |
| Lien absent ou inactif | `302`, `Location: https://profil.mg/{username}` | Non |
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
- `ref` est seulement stocké, après validation comme nom d'hôte. Sans `ref` valide, `referer_domain` reste `NULL`.
- Dans les cas d'indisponibilité, le visiteur retombe sur la page de profil, qui affiche l'état correct.
- `Cache-Control: no-store` garantit qu'une ancienne destination n'est jamais servie après modification.
- Le `robots.txt` de `api.profil.mg` exclut `/r/` et `/api/`, pas `/media/` : les robots doivent pouvoir lire `og:image`.

## Profils publics

### `GET /api/v1/public/profiles/{username}`

Public. Réponse `200` pour un profil actif :

```json
{
  "id": "0b7e9a3e-1f55-4b7a-9d7e-3c1f9e2a4d10",
  "username": "bryan",
  "first_name": "Bryan",
  "last_name": "Rakoto",
  "bio": "Photographe à Antananarivo.",
  "photo_url": "https://api.profil.mg/media/6f1c2a.webp",
  "is_active": true,
  "link_available": true
}
```

`link_available` *(ajout)* indique si le bouton doit s'afficher.

Pour un profil désactivé ou un compte suspendu, la réponse reste `200` et n'expose rien de personnel :

```json
{
  "id": "0b7e9a3e-1f55-4b7a-9d7e-3c1f9e2a4d10",
  "username": "bryan",
  "first_name": null,
  "last_name": null,
  "bio": null,
  "photo_url": null,
  "is_active": false,
  "link_available": false
}
```

Username inconnu : `404`.

**Ne contient jamais** `destination_url`, `email`, `user_id`, ni aucune donnée d'authentification. Le schéma de réponse Pydantic est une liste blanche, et un test parcourt tous les endpoints publics pour le vérifier.

### `POST /api/v1/public/profiles/{username}/visit` *(ajout)*

Public, envoyé par `navigator.sendBeacon`. Sans corps, ce qui évite le preflight CORS.

| Paramètre | Rôle |
|---|---|
| `ref` (query, optionnel) | Domaine extrait de `document.referrer` |

Réponse : `204`, y compris pour un profil inconnu, afin de ne rien révéler. Seul un profil actif génère un enregistrement.

### `GET /api/v1/public/sitemap` *(ajout)*

Public. Utilisé par `app/sitemap.ts`.

```json
[{ "username": "bryan", "updated_at": "2026-11-06T09:00:00Z" }]
```

Profils actifs uniquement, limité à 50 000 entrées.

## Authentification

### `POST /api/v1/auth/register`

```json
{
  "email": "bryan@example.com",
  "password": "un-mot-de-passe-long",
  "password_confirm": "un-mot-de-passe-long",
  "username": "bryan"
}
```

Le champ `username` est un ajout soumis à validation (V2). Mot de passe de 10 à 128 caractères.

- `201`, cookie posé : compte, profil actif et session créés en une transaction. Corps identique à `GET /auth/me`.
- Erreurs : `409 email_taken`, `409 username_taken`, `422 reserved_username`, `422` de validation.

### `POST /api/v1/auth/login`

```json
{ "email": "bryan@example.com", "password": "un-mot-de-passe-long" }
```

- `200`, cookie posé. Corps identique à `GET /auth/me`.
- `401 invalid_credentials`. Un hachage factice est calculé pour un email inconnu, afin que le temps de réponse ne révèle pas son existence.
- Le hachage Argon2 s'exécute dans un thread, pour ne pas bloquer la boucle async.

### `POST /api/v1/auth/logout`

Authentifié. `204`, session supprimée en base et cookie effacé.

### `POST /api/v1/auth/refresh`

Authentifié. Remplace le jeton et repousse l'expiration à 14 jours. `200`, nouveau cookie. Le dashboard l'appelle à l'ouverture s'il reste moins de 7 jours.

### `GET /api/v1/auth/me`

Authentifié.

```json
{
  "id": "7a4e1c7c-9a58-4d6f-8d90-5f3e0a4c1b22",
  "email": "bryan@example.com",
  "username": "bryan",
  "session_expires_at": "2026-11-20T09:00:00Z"
}
```

## Profil propriétaire

Tous les endpoints `/owner/*` exigent une session valide et agissent exclusivement sur le propriétaire de cette session. Aucun identifiant de propriétaire n'est accepté en entrée.

Chaque modification de `/owner/profile*` et de `/owner/links*` invalide le cache de la page publique.

### `GET /api/v1/owner/profile`

```json
{
  "id": "0b7e9a3e-1f55-4b7a-9d7e-3c1f9e2a4d10",
  "username": "bryan",
  "first_name": "Bryan",
  "last_name": "Rakoto",
  "bio": "Photographe à Antananarivo.",
  "photo_url": "https://api.profil.mg/media/6f1c2a.webp",
  "is_active": true,
  "public_url": "https://profil.mg/bryan",
  "created_at": "2026-11-06T09:00:00Z",
  "updated_at": "2026-11-06T09:00:00Z"
}
```

### `PUT /api/v1/owner/profile`

```json
{
  "username": "bryan",
  "first_name": "Bryan",
  "last_name": "Rakoto",
  "bio": "Photographe à Antananarivo."
}
```

`200`, profil complet. Erreurs : `409 username_taken`, `422 reserved_username`.

### `POST /api/v1/owner/profile/photo`

`multipart/form-data`, champ `file`. JPEG, PNG ou WebP, 5 Mo au plus.

Le type est déterminé par le décodage de l'image, pas par le `Content-Type` du client. L'image est recadrée en 512×512, réencodée en WebP et débarrassée de ses métadonnées.

```json
{ "photo_url": "https://api.profil.mg/media/9d3b1e.webp" }
```

Erreurs : `413 file_too_large`, `415 unsupported_image`.

### `PATCH /api/v1/owner/profile/status`

```json
{ "is_active": false }
```

`200`, profil complet.

## Liens externes

Un seul lien par profil : `GET` renvoie 0 ou 1 élément, et un second `POST` répond `409 link_exists`.

```json
{
  "id": "c8b2f0d4-2e1a-4f60-a7d3-1e9b6c5a7f33",
  "destination_url": "https://example.com/external-page",
  "is_active": true,
  "created_at": "2026-11-06T09:00:00Z",
  "updated_at": "2026-11-06T09:00:00Z"
}
```

| Méthode | Route | Corps | Succès |
|---|---|---|---|
| `POST` | `/api/v1/owner/links` | `{ "destination_url": "…" }` | `201`, lien |
| `GET` | `/api/v1/owner/links` | — | `200`, tableau |
| `PUT` | `/api/v1/owner/links/{link_id}` | `{ "destination_url": "…" }` | `200`, lien |
| `DELETE` | `/api/v1/owner/links/{link_id}` | — | `204` |
| `PATCH` | `/api/v1/owner/links/{link_id}/status` | `{ "is_active": false }` | `200`, lien |

### Validation des destinations

Appliquée à l'enregistrement. Tout refus répond `422 invalid_destination`.

| Règle | Exemples refusés |
|---|---|
| Schéma `http` ou `https` | `javascript:`, `data:`, `file:`, `ftp:` |
| URL bien formée, 2 048 caractères au plus | Hôte vide, caractères de contrôle, espaces |
| Pas d'identifiants dans l'URL | `https://paypal.com@evil.test/` |
| Pas de nom local | `localhost`, `*.localhost`, `*.local`, `*.internal`, nom sans point |
| Pas d'IP non publique, sous toutes ses formes | `127.0.0.1`, `10.x`, `192.168.x`, `169.254.169.254`, `[::1]`, `[::ffff:127.0.0.1]`, `2130706433`, `0x7f.1` |
| Pas de boucle vers le service | `profil.mg`, `*.profil.mg` |
| Le domaine se résout, et uniquement vers des IP publiques | Domaine inexistant, domaine pointant vers `10.0.0.5` |

Les noms de domaine sont normalisés en punycode. Le contrôle DNS a lieu à l'enregistrement uniquement, avec un délai court. L'API ne contacte jamais la destination elle-même.

## Statistiques

Fuseau `Indian/Antananarivo`. Aucune réponse ne contient `ip_hash`.

### `GET /api/v1/owner/analytics/overview`

```json
{
  "total_visits": 1240,
  "total_clicks": 372,
  "conversion_rate": 0.3,
  "profile_is_active": true,
  "link_is_active": true,
  "public_url": "https://profil.mg/bryan",
  "recent_activity": [
    {
      "type": "click",
      "occurred_at": "2026-11-06T08:58:00Z",
      "referer_domain": "l.instagram.com"
    }
  ]
}
```

- `conversion_rate` vaut `null` s'il n'y a aucune visite. Il peut dépasser 1 : la valeur n'est pas corrigée.
- `recent_activity` contient les 10 derniers événements.

### `GET /api/v1/owner/analytics/clicks`

| Paramètre | Valeurs | Défaut |
|---|---|---|
| `granularity` | `day`, `week`, `month` | `day` |
| `from`, `to` | Date `YYYY-MM-DD` | 30 derniers jours |
| `limit`, `offset` | Pagination de l'historique, `limit` ≤ 100 | `50`, `0` |

```json
{
  "granularity": "day",
  "timezone": "Indian/Antananarivo",
  "total": 42,
  "series": [
    { "bucket": "2026-11-05", "count": 12 },
    { "bucket": "2026-11-06", "count": 0 }
  ],
  "history": [
    {
      "clicked_at": "2026-11-06T08:58:00Z",
      "referer_domain": "l.instagram.com",
      "user_agent": "Mozilla/5.0 …"
    }
  ]
}
```

Les périodes sans événement sont renvoyées avec `count: 0`, ce qui est leur valeur réelle.

### `GET /api/v1/owner/analytics/visits`

Mêmes paramètres `granularity`, `from` et `to`, même réponse sans `history`.

## Service

### `GET /health` *(ajout)*

Exécute `SELECT 1`. `200 {"status":"ok"}` ou `503`. Utilisé par le healthcheck Docker.

### Route interne `POST /api/revalidate` *(ajout, Next.js)*

Appelée par FastAPI sur le réseau Docker.

```http
POST http://frontend:3000/api/revalidate
X-Revalidate-Secret: <secret>

{ "usernames": ["ancien-nom", "nouveau-nom"] }
```

Exécute `revalidateTag('profile:<username>', { expire: 0 })` pour chaque nom. Nginx bloque `/api/` sur `profil.mg` : la route n'est pas joignable depuis Internet, et le secret reste exigé.

## Rate limiting

Appliqué par Nginx, par IP réelle du visiteur. Valeurs initiales à ajuster sur le trafic constaté, volontairement larges à cause du partage d'IP par les opérateurs mobiles.

| Zone | Limite | Rafale |
|---|---|---|
| `/api/v1/auth/*` | 20/min | 10 |
| `/r/*` | 300/min | 100 |
| `/api/v1/public/*` | 300/min | 100 |
| `/api/v1/owner/*` | 120/min | 40 |
