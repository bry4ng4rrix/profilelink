# Architecture — ProfileLink

> **Statut : modèle administrateur/VA implémenté et testé, non déployé.** Mise à jour : 2026-11-06.
> Voir aussi : [ROADMAP.md](ROADMAP.md), [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md), [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

## 1. Vue d'ensemble

ProfileLink publie les pages individuelles de VA (Virtual Assistants) à l'adresse `profil.mg/<username>`. Un administrateur gère tous les VA depuis un dashboard privé. Le lien externe de chaque VA reste en base et n'est résolu par FastAPI qu'au clic.

```text
 Visiteur (Instagram, Facebook, Google…)        Administrateur
                 │                                   │
                 └─────────────────┬─────────────────┘
                                   ▼
                              Cloudflare        DNS, TLS public, cache des assets
                                   │            Full (strict) + Authenticated Origin Pulls
                                   ▼
                                 Nginx          TLS d'origine, IP réelle, rate limiting, /media
                        ┌──────────┴──────────┐
              profil.mg ▼                     ▼ api.profil.mg
                     Next.js  ── lecture ──▶ FastAPI ──▶ PostgreSQL
                  (rendu, cache) ◀ invalidation ┘         (réseau privé, aucun port publié)
```

Trois règles structurent le reste :

1. **Les visiteurs n'ont jamais de compte.** Pages et redirection n'exigent ni cookie, ni JWT, ni CAPTCHA.
2. **`destination_url` ne sort de PostgreSQL que par deux chemins** : l'en-tête `Location` de `/r/{username}` et les endpoints `/admin/*` authentifiés. Next.js ne la reçoit jamais côté serveur.
3. **L'API ne va jamais chercher une destination sur le réseau.** Elle la valide puis la renvoie au navigateur.

Le lien Instagram d'un VA suit une règle plus stricte encore : il n'existe que dans le dashboard, et aucune réponse publique ne le contient.

La destination n'est pas exposée avant le clic, mais elle devient visible dans la réponse `Location` au moment de la redirection. Aucune promesse de secret après le clic n'est faite.

## 2. Rôles

| | Administrateur | Visiteur | VA |
|---|---|---|---|
| Authentification | Obligatoire | Aucune | Aucune |
| Compte, mot de passe, session | Oui, par CLI ou route protégée | Non | **Non** |
| Dashboard | Oui | Non | **Non** |
| Créer, modifier, supprimer des VA | Oui | Non | Non |
| Gérer les liens externes | Oui | Non | Non |
| Statistiques | Oui | Non | Non |
| Pages publiques et redirection | Oui | Oui | Oui |

Un VA est une **ligne de données**, pas un utilisateur. La table `users` ne contient que des administrateurs.

## 3. Inventaire de la refonte

Ce qui a changé en passant de l'inscription libre au modèle administrateur/VA.

### Conservé tel quel

| Élément | Raison |
|---|---|
| `core/config`, `core/db`, `core/security`, `core/logging` | Indépendants du modèle métier |
| `services/destinations`, `services/photos`, `services/revalidate` | Validation, réencodage et invalidation restent valables |
| `users`, `sessions`, login, logout, refresh, me | Deviennent l'authentification administrateur |
| `/r/{username}` et sa logique | **Répond déjà à la section 4 de la demande** |
| Anti-CSRF, CORS, cookies, journaux | Inchangés, seul le préfixe protégé change |
| `lib/lamba`, `lib/profiles`, `proxy.ts`, `/api/revalidate`, graphiques, `BarChart`, shell | Réutilisables |
| Docker, Compose, sauvegardes, `next.config.ts`, CSP | Validés en production simulée |

### Modifié

| Élément | Changement |
|---|---|
| `models/profile.py` | `Profile` → `VaProfile`, `ExternalLink` → `VaExternalLink`. Retrait de `user_id` et `bio`, ajout de `age` et `instagram_url` |
| `models/event.py` | `profile_id` → `va_profile_id` |
| `core/usernames.py` | Ajout de la génération automatique de l'URL |
| `schemas/*`, `repositories/*` | Alignement sur le nouveau modèle |
| `services/analytics.py` | Portée globale ou par VA |
| `api/public.py` | Ajout de `age`, retrait de `bio` |
| `api/deps.py` | `CurrentProfile` → `CurrentAdmin` |
| `main.py`, `nginx.conf` | Préfixe `/api/v1/owner/` → `/api/v1/admin/` |
| Page publique | Photo, prénom, nom, âge, bouton. Retrait de `@username`, bio et « Créer ma page » |
| 404, `/conditions` | Retrait de toute mention d'inscription, textes réécrits |
| Dashboard, statistiques, navigation | Gestion centralisée de tous les VA |

### Supprimé

| Élément | Raison |
|---|---|
| `POST /api/v1/auth/register`, `RegisterIn` | Plus d'inscription |
| Page `/register`, `register-form` | Plus d'inscription |
| `api/owner_profile.py`, `api/owner_links.py`, `services/profiles.py`, `services/links.py` | Remplacés par `admin_vas` et `services/vas.py` |
| `/dashboard/profile`, `/dashboard/links` | Remplacés par `/dashboard/vas` |
| Page d'accueil, `og-default.png` | `/` redirige vers `/login`, ou vers `/dashboard` avec une session |
| `sitemap.xml`, `GET /public/sitemap` | Les pages ne sont pas indexées |

### Ajouté

| Élément | Rôle |
|---|---|
| `api/admin_vas.py`, `api/admin_analytics.py`, `services/vas.py` | Gestion des VA |
| `app/cli.py` | Création de l'administrateur et réinitialisation du mot de passe |
| Migration Alembic `0002` | Passage au nouveau schéma |
| `/dashboard/vas`, `/dashboard/vas/new`, `/dashboard/vas/[id]` | Liste, ajout, modification |

## 4. Structure du dépôt

```text
profilelink/
├── backend/
│   ├── app/
│   │   ├── main.py            # application, middlewares, routeurs
│   │   ├── cli.py             # comptes administrateur
│   │   ├── core/              # config, db, sécurité, logs, usernames
│   │   ├── models/            # SQLAlchemy
│   │   ├── schemas/           # Pydantic
│   │   ├── repositories/      # requêtes SQL
│   │   ├── services/          # logique métier
│   │   └── api/               # routes et dépendances
│   ├── alembic/
│   └── tests/
├── frontend/                  # dépôt git distinct, référencé par la racine
│   ├── app/
│   │   ├── [username]/        # page publique d'un VA
│   │   ├── (auth)/login/      # connexion administrateur
│   │   ├── dashboard/         # privé, composants client
│   │   └── api/revalidate/    # invalidation appelée par FastAPI
│   ├── components/
│   ├── lib/                   # couche fetch centralisée, schémas Zod
│   ├── proxy.ts               # redirection optimiste vers /login
│   └── e2e/                   # Playwright
├── nginx/
├── scripts/                   # sauvegarde, plages Cloudflare
├── docker-compose.yml         # production
├── docker-compose.dev.yml     # PostgreSQL local
└── .env.example
```

`.venv/` reste à la racine. `frontend/` garde son propre dépôt git, car il contient des commits en cours : le dépôt racine n'en suit donc que la référence.

## 5. Flux principaux

### Création d'un VA

```text
Dashboard ─▶ POST /api/v1/admin/vas (multipart : champs + photo)
                │  valide la destination, réencode la photo, génère le username
                ▼
             Une transaction : va_profiles + va_external_links
                ▼
             Réponse avec public_url → copier / consulter
```

Le VA et son lien sont créés ensemble : les deux sont obligatoires, et un échec ne laisse aucun profil partiel.

### Visite d'une page

1. Le navigateur demande `profil.mg/bryan`.
2. Next lit `getProfile('bryan')`, en cache sous le tag `profile:bryan`, et appelle si besoin l'API sur le réseau Docker.
3. La page est servie complète, sans aucune destination dans le HTML, les métadonnées ou le JavaScript.
4. Un composant client envoie `sendBeacon` pour compter la visite.

### Clic sur le bouton

```text
<a href="https://api.profil.mg/r/bryan" rel="nofollow">
        │  navigation normale du navigateur
        ▼
GET /r/bryan ─▶ VA + lien actifs ? ─ non ─▶ 302 vers profil.mg/bryan (page d'état, aucun clic compté)
                     │ oui
                     ▼
               INSERT click_event ─▶ 302 Location: <destination>, Cache-Control: no-store
```

Si l'`INSERT` échoue, l'erreur est journalisée et la redirection part quand même.

### Modification par l'administrateur

```text
Dashboard ─▶ FastAPI ─▶ COMMIT ─▶ POST http://frontend:3000/api/revalidate (secret partagé)
                                       └─▶ revalidateTag('profile:<username>', { expire: 0 })
```

Si l'appel échoue, il est journalisé et le TTL de 5 minutes sert de filet. La suppression d'un VA invalide aussi sa page, qui répond 404 immédiatement. `/r/` n'est jamais en cache.

### Authentification

`/` ne contient aucune page : `proxy.ts` redirige vers `/login`, ou vers `/dashboard` si un cookie de session existe.

Le navigateur appelle directement `api.profil.mg` avec `credentials: 'include'`. Le dashboard est fait de composants client avec TanStack Query. Next ne lit le cookie que dans `proxy.ts`, pour rediriger sans flash vers `/login` ; la vérification réelle reste dans FastAPI.

## 6. Décisions techniques

### Inchangées

- **D1. Sessions opaques en base.** Cookie `pl_session` de 256 bits, seul son SHA-256 est stocké. Déconnexion et révocation immédiates.
- **D2. Page publique.** `'use cache'` + `cacheTag` + `htmlLimitedBots: /.*/` : même réponse pour tous les User-Agents, OG dans le `<head>`, vrai 404. Aucun `loading.tsx` sur `/[username]`, car le streaming fixerait le statut à 200 avant `notFound()`.
- **D3. Rate limiting par Nginx, sans Redis.** Seuils publics larges, car les opérateurs mobiles partagent des IP entre abonnés.
- **D4. CSRF.** `SameSite=Lax` + contrôle d'`Origin` sur `/auth/*` et `/admin/*`, ce qui couvre aussi les uploads multipart. Une requête de même origine que l'API est acceptée : elle ne peut pas être du CSRF, et c'est ainsi que Swagger appelle l'API.
- **D5. Aucune requête serveur vers les destinations.** « Tester » ouvre l'URL dans l'onglet de l'administrateur.
- **D6. Photos.** Pillow décode, refuse tout sauf JPEG/PNG/WebP, recadre en 800×800 et réencode en WebP sous un nom UUID. Métadonnées et GPS sont supprimés.
- **D7. Cloudflare.** Full (strict), certificat Origin CA, Authenticated Origin Pulls. Un filtrage UFW ne suffirait pas : les ports publiés par Docker le contournent.
- **D8. Tests.** pytest sur un vrai PostgreSQL, Playwright sur le build de production.

### Nouvelles

- **D9. URL générée à la création, puis figée.** Le prénom devient l'adresse (`bryan`). En cas de conflit : `bryan-rakoto`, puis `bryan-rakoto-2`. Les accents sont retirés, et un prénom trop court ou réservé bascule sur prénom + nom. Corriger un nom ne change pas l'URL, donc aucun lien déjà publié ne casse.
- **D10. Un seul lien par VA, obligatoire.** Il se modifie et se désactive, mais ne se supprime pas seul. `va_profile_id` reste `UNIQUE`.
- **D11. Comptes administrateur.** Trois chemins : `python -m app.cli create-admin` sur le serveur, `POST /api/v1/auth/register` dans Swagger, ou la page HTML `/register`, utile en production où `/docs` est désactivé. Aucun n'apparaît dans le frontend, et les deux routes HTTP exigent un code (`REGISTRATION_TOKEN`). Tout compte étant administrateur, ne pas l'afficher ne protège rien : sans code configuré, elles répondent 404. La réinitialisation du mot de passe passe par la CLI, ce qui évite un fournisseur d'email.
- **D12. Statistiques globales ou par VA.** Les endpoints acceptent un `va_id` optionnel.
- **D13. Âge hors des métadonnées.** Il apparaît sur la page, jamais dans Open Graph.
- **D14. Pages non indexées.** `noindex, nofollow` sur chaque page, aucun sitemap. `robots.txt` les laisse accessibles, car un robot bloqué ne lirait ni le `noindex` ni les balises d'aperçu.
- **D15. Relation vers le lien en `lazy="raise"`.** Si un chemin public tentait de lire la destination, il échouerait au lieu de la laisser fuiter.
- **D16. Lien Instagram privé.** Obligatoire, affiché seulement dans le dashboard. Sa validation analyse l'hôte réel, car `instagram.com@evil.test` ou `instagram.com.evil.test` passeraient un simple contrôle de texte.

## 7. Comportement vérifié de Next 16.4

Mesures sur `/[username]` avec `use cache`, `next build` + `next start`, quatre User-Agents.

| Mesure | Next par défaut | `htmlLimitedBots: /.*/` (retenu) |
|---|---|---|
| OG dans le `<head>` | oui pour les 4 | oui pour les 4 |
| Profil inconnu, 1ᵉʳ visiteur | **200 (soft 404)** | 404 |
| `Cache-Control` du HTML | selon le User-Agent | `private, no-store` pour tous |
| Même réponse pour tous | **non** | oui |

- La page 404 a le bon statut et `noindex`, mais son contenu est rendu par JavaScript : son HTML initial est vide de texte visible.
- Ce test simule les robots par leur User-Agent. L'aperçu réel reste à valider avec le débogueur de partage de Meta.

## 8. Écarts validés avec les exemples de la demande

| Exemple | Retenu | Raison |
|---|---|---|
| `/r/` répond `404` JSON si le VA ou le lien est inactif | 302 vers la page du VA | Un visiteur qui clique après une désactivation verrait du JSON brut sur `api.profil.mg`. |
| `<button onClick={window.location.assign(...)}>` | `<a href=".../r/bryan" rel="nofollow">` | Fonctionne sans JavaScript et reste un vrai lien pour le clavier et les lecteurs d'écran. Il ne contient que le username. |

## 9. Risques

| Niveau | Risque | Traitement |
|---|---|---|
| **Élevé** | **Mineurs.** Aucun âge minimum n'est imposé, par décision du 2026-11-06. Un mineur saisi verrait sa photo et son âge publiés. | Responsabilité de l'administrateur. Pour imposer 18 ans : modifier `Age` dans `schemas/va.py`, la contrainte `age_range` par une migration et la règle Zod. |
| **Élevé** | **Données personnelles de tiers.** L'âge et la photo d'une personne deviennent publics, et le VA n'a aucun accès pour les corriger. Le cadre malgache (loi n° 2014-038, à confirmer) et le RGPD pour les visiteurs européens peuvent s'appliquer. | Consentement écrit de chaque VA, conservation à arrêter avec un juriste. `noindex` limite l'exposition. |
| **Élevé** | **Compte administrateur unique point d'entrée.** Une compromission, ou une fuite de `REGISTRATION_TOKEN`, permet de rediriger tous les VA vers n'importe quelle adresse. | Mot de passe long, rate limiting strict sur `/auth/*` et `/register`. Laisser `REGISTRATION_TOKEN` vide hors création de compte. Pas de double authentification en v1. |
| Moyen | **Âge figé.** Un nombre saisi une fois devient faux avec le temps. | Conforme à la demande. Une date de naissance réglerait le problème si besoin. |
| Moyen | **Aucune garantie vis-à-vis de Meta.** Une redirection publique reste suivable, et la page visible peut être évaluée comme toute autre. | Aucune promesse de ce type dans le produit. Pas de cloaking. |
| Moyen | **VPS unique.** | Sauvegardes hors VPS, restauration testée. |
| Faible | **Réemploi d'une URL.** Après suppression d'un VA, son adresse redevient libre et les liens déjà publiés pointeraient vers le prochain VA homonyme. | Accepté en v1. |
| Faible | **Statistiques indicatives.** Le beacon peut être bloqué ou forgé, et le taux clics/visites peut dépasser 100 %. | Affichage sans correction. |
| Faible | **Évolution de Next.** D2 repose sur le comportement actuel. | Tests Playwright sur OG et 404. |

## 10. Décisions

| # | Sujet | Décision |
|---|---|---|
| A1 | Âge minimum | Aucun. Seul un contrôle de cohérence s'applique (1 à 120). |
| A2 | Google | Pages non indexées, pas de sitemap. |
| A3 | Accueil | `/` mène à la connexion, puis au dashboard. |
| A4 | VPS et domaine | **En attente de réponse**, nécessaire avant le déploiement. |
| A5 | VA ou lien inactif sur `/r/` | 302 vers la page du VA |
| A6 | Bouton | `<a>` |
| A7 | Libellé | « Visiter le lien » |
| A8 | Supprimer un VA | Suppression définitive, avec ses statistiques et sa photo, après confirmation |
| A9 | Administrateur | Créé par CLI, ou par Swagger ou la page FastAPI `/register` avec un code, plusieurs comptes possibles, pas de 2FA en v1 |
| A10 | Page publique | Pas de bio ni de `@username`, « Signaler cette page » conservé |
| A11 | Contact d'un VA | L'email est remplacé par un lien Instagram obligatoire, privé, non unique |

## 11. Choix techniques

| Domaine | Choix |
|---|---|
| Frontend | Next 16.4.5, React 19.3, Tailwind 4, shadcn `base-nova`, Lucide, React Hook Form, Zod, TanStack Query, Playwright |
| Backend | Python 3.14, FastAPI 0.162, Pydantic 2.14, SQLAlchemy 2.1 async, asyncpg 0.32, Alembic 1.20, argon2-cffi 25.1, Pillow 13, httpx, pytest |
| Données | PostgreSQL 18 |
| Infra | Docker Compose (`frontend`, `backend`, `postgres`, `nginx`), Cloudflare. Migrations lancées par la commande du conteneur backend. |

`NEXT_PUBLIC_API_URL` est figée à la compilation et passe en argument de `docker build`.

## 12. Hors périmètre

Compte ou dashboard VA, inscription publique sans code, page d'accueil, plusieurs liens par VA, bio, modification de l'URL, double authentification, mot de passe oublié par email, thèmes personnalisés, domaines personnalisés, visiteurs uniques, détection de bots, Redis, déploiement multi-serveurs.
