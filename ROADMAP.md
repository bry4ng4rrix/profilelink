# Roadmap — ProfileLink

> Mise à jour : 2026-11-06. **Phase en cours : 6.5, déploiement en attente des informations VPS et domaine.**
> Ce fichier est mis à jour à la fin de chaque phase. On ne passe à la phase suivante que si ses tests essentiels réussissent.

| Phase | Objectif | Statut |
|---|---|---|
| 1 | Analyse et architecture | Terminée |
| 2 | Backend | Terminée |
| 3 | Frontend | Terminée |
| 4 | SEO et sécurité | Terminée, sauf validation Meta |
| 5 | Production | Validée en local, **pas déployée** |
| 6 | Refonte administrateur/VA | Développée et testée, **pas déployée** |

Les phases 2 à 5 ont été réalisées sur le modèle à inscription libre, remplacé par la phase 6.
État des tests : 312 tests pytest, 70 tests Playwright.

## Phase 6 — Refonte administrateur/VA

### 6.0 Conception

- [x] Inspection de l'existant
- [x] Inventaire : conservé, modifié, supprimé, ajouté ([détails](ARCHITECTURE.md#3-inventaire-de-lexistant))
- [x] Base de référence verte : 190 tests pytest, 56 tests Playwright
- [x] `ARCHITECTURE.md`, `DATABASE_SCHEMA.md`, `API_DOCUMENTATION.md`, `ROADMAP.md`
- [x] Validation de la conception, décisions A1 à A3 et A5 à A11 ([ARCHITECTURE.md](ARCHITECTURE.md#10-décisions))

### 6.1 Données et authentification

- [x] Migration `0002` avec garde-fou sur les données existantes
- [x] Modèles `VaProfile`, `VaExternalLink`
- [x] Suppression de l'inscription
- [x] `app/cli.py` : `create-admin`, `reset-password`
- [x] Tests : aller-retour de migration, `alembic check`, garde-fou, CLI, route d'inscription absente

### 6.2 API d'administration

- [x] Génération de l'URL publique
- [x] `/api/v1/admin/vas` : création atomique, liste, lecture, modification, suppression, photo, statut, lien
- [x] Statistiques globales et par VA
- [x] Champ `age` sur la route publique
- [x] Préfixe protégé dans `main.py` et Nginx

Tests pytest à faire réussir :

- [x] Génération d'URL : conflits, accents, prénoms courts, noms réservés
- [x] Création atomique : un lien ou une photo invalide ne laisse aucun VA
- [x] Accès anonyme et cookie forgé refusés sur **toutes** les routes `/admin/*`
- [x] Destination absente de **toutes** les routes publiques
- [x] Email administrateur absent de toutes les routes publiques
- [x] VA désactivé : aucune donnée personnelle exposée
- [x] Âge hors de 1 à 120 refusé
- [x] Suppression : lien, statistiques et photo effacés, page en 404 immédiat

### 6.3 Dashboard

- [x] `/dashboard/vas` : photo, nom complet, email, URL, copier, consulter
- [x] `/dashboard/vas/new`, `/dashboard/vas/[id]`
- [x] Statistiques avec filtre par VA
- [x] Vue d'ensemble globale
- [x] Retrait de `/dashboard/profile` et `/dashboard/links`

### 6.4 Pages publiques

- [x] Page VA : photo, prénom, nom, âge, bouton
- [x] `/` vers la connexion, 404 et `/conditions` sans inscription
- [x] Retrait de `/register`
- [x] `noindex` sur les pages, sitemap retiré

Tests Playwright à faire réussir :

- [x] Parcours complet : connexion, création d'un VA, page publique, clic, statistiques
- [x] Aucune trace d'inscription sur l'accueil, `/register` en 404
- [x] Aucune destination dans le HTML, les métadonnées, le JavaScript ou le JSON public
- [x] Âge absent d'Open Graph
- [x] Lien Instagram absent de la page, du JSON et du JavaScript publics
- [x] Modification visible immédiatement sur la page publique
- [x] Responsive sur tous les écrans du dashboard

### 6.5 Mise en production

- [x] Reprise du test Docker complet sur le nouveau modèle
- [x] `SECURITY.md`, `DEPLOYMENT.md`, `README.md`
- [ ] Déploiement sur le VPS, **après réponse à A4 et autorisation explicite**
- [ ] Vérifications en production, débogueur de partage Meta

## Phases terminées

### Phase 2 — Backend

- [x] FastAPI, SQLAlchemy async, Alembic, sessions, profils, liens, redirection, statistiques
- [x] Tests pytest sur PostgreSQL 18, migration aller-retour, `alembic check`

### Phase 3 — Frontend

- [x] Design system, page publique et ses états, connexion, dashboard, graphiques
- [x] Tests Playwright sur le build de production, mobile et bureau

### Phase 4 — SEO et sécurité

- [x] Métadonnées, Open Graph, canonique, `noindex` des profils désactivés, sitemap, robots
- [x] CSP, `nosniff`, `Referrer-Policy`, HSTS
- [ ] Validation réelle avec le débogueur de partage Meta

### Phase 5 — Production

Validé sur la pile Docker complète, en mode production, sur cette machine :

- [x] Dockerfiles, Compose, réseaux privés, volumes, healthchecks
- [x] Nginx : TLS, certificat client, IP réelle, rate limiting, `/media`, `/api/` bloqué sur `profil.mg`
- [x] Accès direct à l'origine refusé, cookie `Secure`, usurpation d'IP sans effet, aucune destination dans les logs
- [x] Sauvegarde et **restauration testées**, persistance après `down`/`up`, conteneur recréé retrouvé par Nginx

Reste à faire, sur le VPS, en 6.5 :

- [ ] Cloudflare, vrai certificat d'origine, pare-feu, SSH, copie des sauvegardes hors VPS

## Journal des décisions

| Date | Décision |
|---|---|
| 2026-11-06 | Conception basée sur l'existant (Next 16.4, shadcn `base-nova`, FastAPI, Python 3.14). Cache Components conservé avec `htmlLimitedBots: /.*/`, après test sur prototype. |
| 2026-11-06 | Implémentation lancée sur les recommandations V1 à V4. `frontend/.git` conservé, car ce dépôt reçoit des commits en cours. Mot de passe oublié et Turnstile non implémentés, faute de fournisseur. |
| 2026-11-06 | Passage au modèle administrateur/VA : plus d'inscription, les VA n'ont pas de compte. Conception validée. |
| 2026-11-06 | Accueil remplacé par une redirection vers la connexion. Pages VA en `noindex`, sitemap retiré. Aucun âge minimum imposé, à la demande de l'utilisateur. |
| 2026-11-06 | L'email des VA est remplacé par un lien Instagram privé, jamais affiché publiquement (migration `0003`). |
| 2026-11-06 | Inscription administrateur ajoutée à FastAPI, visible dans Swagger et absente du frontend. Protégée par `REGISTRATION_TOKEN`, car tout compte est administrateur. |
| 2026-11-06 | FastAPI passe dans Docker en développement (`docker-compose.dev.yml`), à la place d'uvicorn lancé à la main. |
| 2026-11-06 | Base de développement `profilelink_va` créée : la migration `0002` a refusé `profilelink`, qui contenait un compte de test, conservé. |
