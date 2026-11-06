# Architecture — ProfileLink

> **Statut : proposition en attente de validation (phase 1).** Mise à jour : 2026-11-06.
> Voir aussi : [ROADMAP.md](ROADMAP.md), [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md), [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

## 1. Vue d'ensemble

ProfileLink sert des pages de profil publiques (`profil.mg/<username>`), un dashboard privé pour leurs propriétaires et une redirection externe résolue uniquement côté serveur.

```text
 Visiteur (Instagram, Facebook, Google…)        Propriétaire
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

Trois règles structurent tout le reste :

1. **Les visiteurs n'ont jamais de compte.** Profils et redirection n'exigent ni cookie, ni JWT, ni CAPTCHA.
2. **`destination_url` ne sort de PostgreSQL que par deux chemins** : l'en-tête `Location` de `/r/{username}` et les endpoints `/owner/*` authentifiés. Next.js ne la reçoit jamais côté serveur.
3. **L'API ne va jamais chercher une destination sur le réseau.** Elle la valide puis la renvoie au navigateur.

## 2. Structure du dépôt

### État constaté

| Élément | Constat |
|---|---|
| `frontend/` | Next 16.4.5, React 19.3.0, Tailwind 4, shadcn `base-nova` (Base UI), pnpm 12. Possède son propre `.git` (1 commit `create-next-app` + modifications non commitées). |
| `main.py` | Hello World FastAPI. |
| `app/` | Vide. |
| `Dockerfile`, `requiriment.txt` | Vides ; le second a une faute dans le nom. |
| `.venv/` | Python 3.14.8, FastAPI 0.162.0 seul, **sans uvicorn**. |
| `.env` | **Absent.** |
| Racine | Pas un dépôt git. |

### Structure cible

```text
profilelink/
├── backend/
│   ├── app/
│   │   ├── main.py            # application, middlewares, routeurs
│   │   ├── core/              # config, db, sécurité, logs
│   │   ├── models/            # SQLAlchemy
│   │   ├── schemas/           # Pydantic
│   │   ├── repositories/      # requêtes SQL
│   │   ├── services/          # logique métier
│   │   └── api/               # routes et dépendances
│   ├── alembic/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── [username]/        # page publique
│   │   ├── (auth)/            # /login, /register
│   │   ├── dashboard/         # privé, composants client
│   │   └── api/revalidate/    # invalidation appelée par FastAPI
│   ├── components/
│   ├── lib/                   # couche fetch centralisée, schémas Zod
│   ├── proxy.ts               # redirection optimiste vers /login
│   ├── e2e/                   # Playwright
│   └── Dockerfile
├── nginx/
├── docker-compose.yml
├── .env.example
└── README.md, ROADMAP.md, ARCHITECTURE.md, API_DOCUMENTATION.md,
    DATABASE_SCHEMA.md, SECURITY.md, DEPLOYMENT.md
```

Chaque fichier existant de la racine est un point de départ vide ou un stub, le déplacement ne perd donc rien. Le `.venv` doit être recréé, car un venv contient des chemins absolus.

## 3. Flux principaux

### Visite d'un profil

1. Le navigateur demande `profil.mg/bryan`.
2. Next lit `getProfile('bryan')`, en cache sous le tag `profile:bryan`, et appelle si besoin `http://backend:8000/api/v1/public/profiles/bryan` sur le réseau Docker.
3. La page est servie complète : balises OG dans le `<head>`, aucune destination dans le HTML.
4. Un composant client envoie `sendBeacon` vers `POST api.profil.mg/api/v1/public/profiles/bryan/visit?ref=<domaine>`.

La visite est comptée par le navigateur et non par le rendu serveur, sinon les pages en cache ne compteraient pas et FastAPI verrait l'IP de Next au lieu de celle du visiteur.

### Clic sur « Visiter mon lien »

```text
<a href="https://api.profil.mg/r/bryan" rel="nofollow">
        │  navigation normale du navigateur
        ▼
GET /r/bryan ─▶ profil + lien actifs ? ─ non ─▶ 302 vers profil.mg/bryan (page d'état, aucun clic compté)
                     │ oui
                     ▼
               INSERT click_event ─▶ 302 Location: <destination>, Cache-Control: no-store
```

C'est un simple `<a>` : il marche sans JavaScript, dans les navigateurs intégrés d'Instagram et de Facebook, et sans préchargement. `next/link` est exclu, car il précharge. Si l'`INSERT` échoue, l'erreur est journalisée et la redirection part quand même : un clic perdu vaut mieux qu'un visiteur bloqué.

### Modification par le propriétaire

```text
Dashboard ─▶ FastAPI ─▶ COMMIT ─▶ POST http://frontend:3000/api/revalidate (secret partagé)
                                       └─▶ revalidateTag('profile:<username>', { expire: 0 })
```

Si l'appel échoue, il est journalisé et le TTL de 5 minutes sert de filet. Un changement de username invalide l'ancien et le nouveau tag. `/r/` n'est jamais en cache et reflète donc toute modification immédiatement.

### Authentification propriétaire

Le navigateur appelle directement `api.profil.mg` avec `credentials: 'include'`. Le dashboard est fait de composants client avec TanStack Query. Next ne lit le cookie que dans `proxy.ts`, pour rediriger sans flash vers `/login` ; la vérification réelle reste dans FastAPI. Aucune donnée privée ne passe donc par le rendu serveur, et le dashboard échappe aux contraintes de Cache Components sur `cookies()`.

## 4. Décisions techniques

### D1. Sessions opaques en base plutôt que JWT

Un cookie unique `pl_session` porte un jeton aléatoire de 256 bits ; seul son SHA-256 est stocké dans `sessions`.

- **Pourquoi :** la déconnexion et la révocation sont immédiates. Un JWT avec refresh exigerait de toute façon une table pour révoquer, plus une gestion de clés et une rotation : c'est strictement plus de code.
- **Coût :** une requête indexée par appel `/owner/*`. Les routes publiques n'en font aucune.
- `POST /auth/refresh` est conservé : il fait tourner le jeton et prolonge la session.

### D2. Page publique : cache de données + `htmlLimitedBots: /.*/`

Le projet a `cacheComponents: true`, qui devient le comportement par défaut à la prochaine version majeure. Cela impose trois choses, testées sur un prototype Next 16.4.5 (section 5) :

```ts
// next.config.ts
htmlLimitedBots: /.*/,   // métadonnées bloquantes pour tous : même réponse quel que soit le User-Agent
output: 'standalone',

// app/[username]/page.tsx
export async function generateStaticParams() {
  return [{ username: '__shell__' }]   // Cache Components refuse un tableau vide ;
}                                      // refusé par la regex, donc aucun appel API au build
```

`getProfile()` utilise `'use cache'`, `cacheTag` et `cacheLife({ stale: 60, revalidate: 300, expire: 3600 })`. `params` est attendu hors de tout `<Suspense>`, et la route n'a pas de `loading.tsx` : une frontière de streaming fixerait le statut à 200 avant `notFound()`. Le skeleton de la page publique se limite donc à la photo ; le dashboard, lui, a de vrais skeletons.

### D3. Rate limiting par Nginx, sans Redis

`limit_req` couvre le besoin avec zéro dépendance et zéro code applicatif. Redis reste inutile tant qu'il n'y a qu'un VPS. Les seuils doivent rester larges : les opérateurs mobiles partagent souvent une même IP entre beaucoup d'abonnés (CGNAT), et un seuil serré bloquerait de vrais visiteurs.

### D4. CSRF : `SameSite=Lax` + contrôle d'`Origin`

Le cookie est `HttpOnly; Secure; SameSite=Lax; Domain=profil.mg`. `profil.mg` et `api.profil.mg` étant same-site, il n'y a pas de jeton CSRF à gérer. Un middleware rejette toute méthode non-GET sur `/auth/*` et `/owner/*` dont l'`Origin` n'est pas autorisée. Il protège aussi l'upload multipart, qui ne déclenche pas de preflight CORS.

### D5. Aucune récupération serveur des destinations

« Tester la destination » ouvre l'URL dans un nouvel onglet du propriétaire. Le statut affiché est actif/désactivé, sans ping. L'API n'émettant aucune requête vers ces URL, il n'y a pas de surface SSRF à l'exécution. La validation à l'enregistrement reste complète : voir [API_DOCUMENTATION.md](API_DOCUMENTATION.md#validation-des-destinations).

### D6. Photos : volume local, réencodage systématique

Pillow décode l'image, refuse tout sauf JPEG/PNG/WebP, redresse selon l'EXIF, recadre en 512×512 et réencode en WebP sous un nom UUID. Cela supprime les métadonnées (y compris le GPS) et les fichiers polyglottes. Nginx sert `/media/` depuis un volume partagé, avec un cache long, car chaque upload produit un nouveau nom. L'image étant déjà optimisée, `next/image` tourne en `unoptimized` : ni `sharp` ni charge CPU côté Next.

### D7. Cloudflare

- TLS **Full (strict)** avec un certificat Origin CA sur Nginx : pas de certbot.
- **Authenticated Origin Pulls** pour réserver l'origine à Cloudflare. Un filtrage UFW ne suffit pas : les ports publiés par Docker contournent UFW.
- `set_real_ip_from` limité aux plages Cloudflare, et FastAPI ne fait confiance qu'à Nginx pour l'IP.
- Cache uniquement `/_next/static/*` et `/media/*`. Ne jamais activer de règle « Cache Everything » sur le HTML.

### D8. Tests

- **pytest sur un vrai PostgreSQL** : pas de SQLite, dont les types et les contraintes diffèrent.
- **Playwright seul côté frontend** : il couvre formulaires, parcours et responsive sur la vraie pile. Le brief autorise « Vitest ou Playwright » ; un seul outil suffit.

## 5. Résultats du prototype

Prototype jetable, supprimé après mesure. Page `/[username]` avec `use cache`, `next build` + `next start`, quatre User-Agents (WebView Instagram, Chrome, `facebookexternalhit`, Googlebot).

| Mesure | Next par défaut | `htmlLimitedBots: /.*/` (retenu) |
|---|---|---|
| OG dans le `<head>`, profil existant | oui pour les 4 | oui pour les 4 |
| `/nobody`, 1ᵉʳ visiteur | **200 (soft 404)** | 404 |
| `/nobody`, visiteurs suivants | 404 | 404 |
| `Cache-Control` du HTML | `s-maxage=300` ou `private` selon le UA | `private, no-store` pour tous |
| Même réponse quel que soit le UA | **non** | oui |

Mesures complémentaires sur la configuration retenue :

- `next build` réussit **sans API joignable**, condition d'un `docker build`.
- 6 requêtes sur la page produisent 1 seul appel API : le cache de données fonctionne même si le HTML est `private`.
- Après modification en base, `revalidateTag(tag, { expire: 0 })` sert la nouvelle valeur dès la requête suivante.

**Limite :** ce test simule le crawler par son User-Agent sur un serveur local. L'aperçu réel doit être validé en phase 4 avec le débogueur de partage de Meta.

## 6. Écarts par rapport au brief

| # | Brief | Proposition | Raison |
|---|---|---|---|
| E1 | `/register` : email + mots de passe | Ajout du champ **username** | `profiles.username` est `NOT NULL` : sans lui, il faudrait un username fictif ou une étape d'onboarding. |
| E2 | 5 tables | Ajout de **`sessions`** | Déconnexion et révocation réelles (D1). |
| E3 | Profil public : 7 champs | Ajout de **`link_available`** (booléen) | Le brief exige un état « lien indisponible » que les 7 champs ne permettent pas d'afficher. Ne révèle pas la destination. |
| E4 | Aucune route d'enregistrement des visites | `POST /public/profiles/{username}/visit` | Sans elle, `profile_visits` reste vide. |
| E5 | `sitemap.xml` demandé | `GET /public/sitemap` | Next ne doit pas lire la base directement. |
| E6 | `GET /r/{username}` | Paramètre optionnel **`?ref=<domaine>`** | Sur `/r/`, le `Referer` vaut toujours `profil.mg` : `click_events.referer_domain` serait inutile. Stocké seulement, sans effet sur la redirection. |
| E7 | — | `GET /health`, route interne `/api/revalidate` | Healthchecks Docker ; invalidation du cache. |
| E8 | `TIMESTAMP` | `TIMESTAMPTZ` | Évite toute ambiguïté de fuseau dans les statistiques. |
| E9 | PyJWT ou session | Session opaque | Le brief l'autorise (D1). |
| E10 | Vitest ou Playwright | Playwright | Le brief l'autorise (D8). |

## 7. Risques

| Niveau | Risque | Traitement proposé |
|---|---|---|
| **Élevé** | **Abus.** Inscription libre + destination cachée au visiteur = outil idéal pour le phishing. Un signalement peut faire bloquer **tout le domaine** par Meta, Google Safe Browsing ou les navigateurs, donc tous les propriétaires. Le brief ne prévoit ni modération ni administration. | Décision V6. |
| **Élevé** | **Pas de récupération de compte** : sans email sortant, un mot de passe oublié verrouille le profil définitivement. | Décision V5. |
| Moyen | **Aucune garantie vis-à-vis de Meta.** Une redirection publique reste suivable par un robot, et la page visible peut être évaluée comme toute autre. | Aucune promesse de ce type dans le produit. Pas de cloaking. |
| Moyen | **Données personnelles.** `ip_hash` et `user_agent` restent des données liées à une personne. Le cadre malgache (loi n° 2014-038, à confirmer) et le RGPD pour les visiteurs européens peuvent s'appliquer. | HMAC avec clé secrète, jamais d'IP brute. Politique de confidentialité et durée de conservation à arrêter avec un juriste. |
| Moyen | **Changement de username.** Les liens déjà publiés cassent, et l'ancien nom redevient libre : un tiers peut le reprendre et récupérer ce trafic. | Accepté en v1, à documenter dans le dashboard. Historique et délai de carence si le problème apparaît. |
| Moyen | **VPS unique** : point de défaillance unique. | Sauvegardes `pg_dump` + volume `media` hors du VPS, restauration testée en phase 5. |
| Faible | **Statistiques indicatives.** Le beacon peut être bloqué ou forgé, le propriétaire compte ses propres visites, et le taux clics/visites peut dépasser 100 %. | Affichage sans correction ni clamp, libellé honnête. Rate limiting contre les abus grossiers. |
| Faible | **DNS changeant.** Un domaine validé peut pointer plus tard vers une IP privée. | Sans impact serveur (D5) : seul le navigateur du visiteur suit la redirection. |
| Faible | **Évolution de Next.** D2 repose sur le comportement actuel de Cache Components. | Un test Playwright vérifie OG dans le `<head>` et vrai 404. |
| Faible | **Passage à plusieurs instances Next.** `revalidateTag` n'agit que sur l'instance appelée. | Une seule instance en v1. Il faudrait un cache handler partagé. |

## 8. Décisions à valider

| # | Décision | Recommandation |
|---|---|---|
| V1 | Organisation du dépôt | Déplacer le backend dans `backend/`, initialiser git à la racine, supprimer `frontend/.git` (un seul commit généré), après avoir commité l'existant. |
| V2 | Username à l'inscription (E1) | Oui. |
| V3 | Sessions opaques ou JWT (D1) | Sessions opaques. |
| V4 | Autres ajouts au contrat (E2 à E8) | Tous acceptés. |
| V5 | Mot de passe oublié en v1 | Oui, avec un fournisseur d'email transactionnel, ce qui ajoute aussi la vérification d'email. Sans cela, réinitialisation manuelle par SQL. |
| V6 | Anti-abus en v1 | Minimum : CGU, adresse de signalement, suspension par `users.is_active`, Cloudflare Turnstile sur `/register` uniquement (jamais pour les visiteurs). Option à étudier : contrôle Google Safe Browsing à l'enregistrement. |
| V7 | VPS et domaine | Réponses nécessaires : le VPS héberge-t-il déjà des services, notamment sur les ports 80/443 ? `profil.mg` est-il enregistré, et sa délégation vers Cloudflare est-elle possible ? |

## 9. Choix techniques

Versions lues sur npm et PyPI le 2026-11-06 ou sur le disque du projet.

| Domaine | Choix |
|---|---|
| Frontend | Next 16.4.5, React 19.3, Tailwind 4, shadcn `base-nova`, Lucide. À ajouter : `react-hook-form`, `@hookform/resolvers`, `zod`, `@tanstack/react-query`, `@playwright/test`. |
| Backend | Python 3.14, FastAPI 0.162, Pydantic 2.14, SQLAlchemy 2.1 async, asyncpg 0.32, Alembic 1.20, argon2-cffi 25.1. À ajouter : `uvicorn`, `pydantic-settings`, `email-validator`, `python-multipart`, `pillow`, `httpx`, `pytest`. |
| Données | PostgreSQL 18, déjà la version installée en local. |
| Infra | Docker Compose (`frontend`, `backend`, `postgres`, `nginx`), Cloudflare. Migrations lancées par la commande du conteneur backend (`alembic upgrade head && uvicorn …`), sans service dédié. |

Réglages à modifier dans `frontend/next.config.ts` en phase 3 :

- Ajouter `htmlLimitedBots` et `output: 'standalone'`.
- Retirer `experimental.agentFeedback`, activé par `create-next-app`. Il sert à préparer des rapports d'anomalies Next.js via un agent, sans utilité pour ce produit.
- Mettre `lang="fr"` et de vraies métadonnées dans `app/layout.tsx`.

`NEXT_PUBLIC_API_URL` est figée à la compilation et doit donc être passée en argument de `docker build`.

## 10. Hors périmètre de la v1

Plusieurs liens par profil, thèmes personnalisés, domaines personnalisés, visiteurs uniques, détection de bots, tableau d'administration, Redis, CDN d'images, déploiement multi-serveurs.
