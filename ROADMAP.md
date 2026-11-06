# Roadmap — ProfileLink

> Mise à jour : 2026-11-06. **Phase en cours : 1, en attente de validation.**
> Ce fichier est mis à jour à la fin de chaque phase. On ne passe à la phase suivante que si ses tests essentiels réussissent.

| Phase | Objectif | Statut |
|---|---|---|
| 1 | Analyse et architecture | Documents livrés, **validation attendue** |
| 2 | Backend | À faire |
| 3 | Frontend | À faire |
| 4 | SEO et sécurité | À faire |
| 5 | Production | À faire |

## Phase 1 — Analyse et architecture

- [x] Examiner le répertoire de travail et l'existant
- [x] Vérifier le comportement de Next 16.4 sur un prototype (Open Graph, statut 404, invalidation)
- [x] `ARCHITECTURE.md`
- [x] `DATABASE_SCHEMA.md`
- [x] `API_DOCUMENTATION.md`
- [x] `ROADMAP.md`
- [ ] **Validation des décisions V1 à V7** ([ARCHITECTURE.md](ARCHITECTURE.md#8-décisions-à-valider))

## Phase 2 — Backend

Mise en place :

- [ ] Réorganiser le dépôt : `backend/`, git à la racine, `.gitignore`, `.env.example` (après V1)
- [ ] Recréer le venv, renseigner `requirements.txt` et `.env`
- [ ] Configurer PostgreSQL de développement (Compose), SQLAlchemy async, Alembic
- [ ] Logs JSON structurés, sans IP brute ni destination

Fonctionnalités :

- [ ] Modèles et migration initiale
- [ ] Authentification : register, login, logout, refresh, me, contrôle d'`Origin`
- [ ] Profils : public, propriétaire, statut
- [ ] Upload et réencodage des photos
- [ ] Liens : CRUD, statut, validation des destinations
- [ ] Redirection `/r/{username}` et enregistrement des clics
- [ ] Enregistrement des visites et sitemap
- [ ] Statistiques
- [ ] Appel d'invalidation vers Next

Tests pytest, à faire réussir avant la phase 3 :

- [ ] Inscription, connexion, sessions expirées et révoquées
- [ ] Permissions et isolation entre propriétaires
- [ ] CRUD profils et liens
- [ ] Redirection 302, profil désactivé, lien désactivé, `Cache-Control: no-store`
- [ ] Destinations invalides : toute la table de validation
- [ ] Absence de `destination_url` et d'`email` sur **tous** les endpoints publics
- [ ] Accès public sans cookie, accès non autorisé
- [ ] CORS et contrôle d'`Origin`
- [ ] `alembic upgrade head` sur base vide, puis `alembic check`

## Phase 3 — Frontend

- [ ] Ajouter `react-hook-form`, `@hookform/resolvers`, `zod`, `@tanstack/react-query`, `@playwright/test`
- [ ] Ajuster `next.config.ts` et `app/layout.tsx` ([détails](ARCHITECTURE.md#9-choix-techniques))
- [ ] Design system : tokens, typographie, composants partagés
- [ ] Couche `fetch` centralisée et `proxy.ts`
- [ ] Page publique `/[username]` et ses états : actif, introuvable, désactivé, lien indisponible
- [ ] `/register`, `/login`
- [ ] `/dashboard`, `/dashboard/profile`, `/dashboard/links`, `/dashboard/analytics`
- [ ] Pages 404 et erreurs, états vides, skeletons
- [ ] Route `/api/revalidate`

Tests Playwright sur la pile réelle :

- [ ] Formulaires et messages d'erreur
- [ ] Profils publics et bouton de redirection
- [ ] Dashboard : parcours complet
- [ ] États d'erreur
- [ ] Responsive : mobile, tablette, bureau

## Phase 4 — SEO et sécurité

- [ ] `generateMetadata`, Open Graph, URL canonique, `noindex` pour les profils désactivés
- [ ] `sitemap.xml` et `robots.txt`
- [ ] Test : OG dans le `<head>` et vrai 404 pour tous les User-Agents, sur cache froid
- [ ] Test : aucune destination dans le HTML, le JSON ni les métadonnées
- [ ] En-têtes de sécurité : CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`
- [ ] `SECURITY.md`
- [ ] Revue de sécurité de l'ensemble

## Phase 5 — Production

Rien n'est modifié sur le VPS sans autorisation.

- [ ] Dockerfiles backend et frontend (`standalone`)
- [ ] `docker-compose.yml` : réseaux privés, volumes, healthchecks, redémarrage, Postgres sans port publié
- [ ] Nginx : hôtes, IP réelle, rate limiting, `/media`, blocage de `/api/` sur `profil.mg`
- [ ] Cloudflare : DNS, Full (strict), Authenticated Origin Pulls, règles de cache
- [ ] VPS : pare-feu, SSH, déploiement reproductible
- [ ] Sauvegardes hors VPS `pg_dump` + `media`, **restauration testée**
- [ ] `DEPLOYMENT.md`, `README.md`
- [ ] Vérifications en production : redirection, cache, HTTPS, port Postgres fermé depuis Internet
- [ ] Débogueur de partage Meta sur un vrai profil

## Hors périmètre de la v1

Voir [ARCHITECTURE.md](ARCHITECTURE.md#10-hors-périmètre-de-la-v1).

## Journal des décisions

| Date | Décision |
|---|---|
| 2026-11-06 | Phase 1 : conception basée sur l'existant (Next 16.4, shadcn `base-nova`, FastAPI, Python 3.14). Cache Components conservé avec `htmlLimitedBots: /.*/`, après test sur prototype. |
