# ProfileLink

Pages publiques de VA (`profil.mg/<username>`), gérées par un administrateur depuis un dashboard privé. Le bouton de chaque page redirige vers un lien externe stocké côté serveur.

| | |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind 4, shadcn/ui |
| Backend | FastAPI, SQLAlchemy async, Alembic, Python 3.14 |
| Données | PostgreSQL 18 |
| Production | Docker Compose, Nginx, Cloudflare |

## Développement

Prérequis : Python 3.14, Node 26, pnpm 12, Docker.

**1. Base de données**

```bash
docker compose -f docker-compose.dev.yml up -d --wait
```

**2. Configuration**

`.env` à la racine, à ne jamais commiter :

```bash
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://profilelink:profilelink@localhost:5433/profilelink_va
IP_HASH_KEY=<openssl rand -hex 32>
REVALIDATE_SECRET=<openssl rand -hex 32>
REGISTRATION_TOKEN=<openssl rand -hex 32>
FRONTEND_ORIGIN=http://localhost:3000
FRONTEND_INTERNAL_URL=http://localhost:3000
API_PUBLIC_URL=http://localhost:8000
```

`frontend/.env.local` :

```bash
BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
REVALIDATE_SECRET=<la même valeur>
```

**3. Backend**

Il tourne dans Docker, sur le port 8000, et applique les migrations au démarrage :

```bash
docker compose -f docker-compose.dev.yml up -d --build --wait backend
```

| Besoin | Commande |
|---|---|
| Redémarrer | `docker compose -f docker-compose.dev.yml restart backend` |
| Prendre en compte du code modifié | `docker compose -f docker-compose.dev.yml up -d --build --wait backend` |
| Journaux | `docker compose -f docker-compose.dev.yml logs -f backend` |
| Créer un administrateur | `docker compose -f docker-compose.dev.yml exec backend python -m app.cli create-admin admin@example.com` |

Pour lancer les tests, installez aussi l'environnement Python :

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
```

**4. Frontend**

```bash
cd frontend
pnpm install
pnpm dev
```

Ouvrez <http://localhost:3000>.

Un administrateur peut aussi se créer avec le code `REGISTRATION_TOKEN`, dans Swagger (<http://localhost:8000/docs>, route `POST /api/v1/auth/register`) ou sur <http://localhost:8000/register>. Ces deux voies n'existent pas dans le frontend.

## Tests

Ils utilisent la base `profilelink_test`, **vidée à chaque lancement**.

```bash
cd backend && ../.venv/bin/python -m pytest
cd frontend && pnpm test:e2e
```

Les tests E2E tournent sur le build de production, ports 3100 et 8100, avec Google Chrome.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) : architecture, décisions, risques
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) : contrat de l'API
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) : schéma et migrations
- [SECURITY.md](SECURITY.md) : mesures, limites, liste avant mise en ligne
- [DEPLOYMENT.md](DEPLOYMENT.md) : déploiement et sauvegardes
- [ROADMAP.md](ROADMAP.md) : avancement
