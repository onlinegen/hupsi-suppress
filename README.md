# HUPSI Suppress

Ein-Zweck-Tool für den Kunden HUPSI: E-Mail-Adresse eingeben → Klick →
Profil wird im HUPSI-Klaviyo-Account suppressed (erhält keine Mails mehr).

- **Live:** https://hupsi.onlinegen.de (IONOS VPS 217.154.199.198, `/opt/hupsi-suppress`)
- **Login:** gemeinsames Passwort (`HUPSI_PASSWORD` in `deploy/.env` auf dem Server)
- **Stack:** FastAPI (ein Container, serviert auch das Frontend — eine HTML-Datei,
  kein Build), HTTPS über den gemeinsamen Caddy des Sale-Report-Stacks
  (Block siehe `deploy/Caddyfile-block.txt`). Folgt der Blaupause in
  `onlinegen-klaviyo-sale-report/docs/BLUEPRINT.md`, Abweichungen wie bei Alma.
- **Klaviyo:** `POST /api/profile-suppression-bulk-create-jobs` (Revision 2025-07-15),
  Key braucht Scope *Subscriptions: Write*. Key nur serverseitig.

## Lokal entwickeln

```bash
scripts/dev.sh   # http://127.0.0.1:8040, Passwort "test"
```

Ohne `KLAVIYO_API_KEY` antwortet `/api/suppress` mit einem Konfigurations-Fehler —
Login/UI lassen sich trotzdem testen.

## Deploy

```bash
git commit && git push
rsync -az --exclude .venv --exclude __pycache__ --exclude data --exclude .git \
      ./ root@217.154.199.198:/opt/hupsi-suppress/
ssh root@217.154.199.198 'cd /opt/hupsi-suppress && docker compose -f deploy/docker-compose.prod.yml up -d --build'
```

Voraussetzungen einmalig: DNS-A-Record `hupsi` → 217.154.199.198 bei IONOS,
Caddy-Block eintragen (siehe oben), `deploy/.env` auf dem Server befüllen.
