# Deploy runbook — AWS Lightsail

The stack runs on one instance. Postgres and MongoDB are containers on the same
box, so there is nothing else to sign up for.

The instance is meant to be **disposable**: bring it up for a week when it is
needed, snapshot it, delete it. A Lightsail bundle is billed by the hour up to
the monthly cap, and a **stopped instance is still billed in full** — only
deleting stops the charge.

---

## Costs

2 GB bundle = $12/month cap = **$0.0164/hour**.

| | | |
|---|---|---|
| One week running | 168 h × $0.0164 | **$2.76** |
| Two months parked as a snapshot | ~5 GB × $0.05 × 2 | **$0.50** |
| **Two months off, one week on** | | **≈ $3.30** |
| Same period, instance merely *stopped* | 2 × $12 + $2.76 | ~$26.80 ❌ |

Snapshot size tracks data actually written (~5 GB: OS, images, a little data),
not the 60 GB the bundle allocates.

---

## First time

**1. Create the instance**

Lightsail console → *Create instance*

| Setting | Value |
|---|---|
| Blueprint | **OS only → Ubuntu 24.04 LTS** |
| Bundle | **$12 / 2 GB RAM / 2 vCPU** |
| Name | `semantic-rag-search` |

**2. Open port 80**

Instance → *Networking* → IPv4 firewall. HTTP/80 is usually there by default;
add it if not. Nothing else needs opening — only the web container publishes a
port.

**3. Set a billing alarm before anything else**

AWS Billing → *Budgets* → create a $5 monthly budget with an email alert.
Credits cover the bill until they run out; the first real charge should arrive
as an email, not as a surprise. On a new account this is also one of the
onboarding tasks that earns $20 of credit.

**4. Deploy**

Connect via the browser SSH button, then:

```bash
sudo apt-get update -qq && sudo apt-get install -y -qq git
git clone https://github.com/<you>/semantic-rag-search.git
cd semantic-rag-search
sudo bash deploy/setup.sh
```

It stops and asks for a key. Add it and run the script again:

```bash
nano .env        # GEMINI_API_KEY=...   LLM_PROVIDER=gemini
sudo bash deploy/setup.sh
```

First build takes 5–10 minutes — the Python image installs torch. Afterwards
the script prints the URL.

---

## Pausing

Two ways, depending on whether you want the bill to be exactly zero.

### A. Delete everything — $0.00/month

Nothing is kept, because nothing needs to be: the code is in git and the notes
are in `seed/`. This is the reason `setup.sh` and `seed.sh` exist.

```
Instance → Manage → Delete
Snapshots → delete any snapshots
Networking → release any static IP that is not attached
```

All three matter. A snapshot costs ~$0.05/GB/month and an unattached static IP
is billed by the hour, so leaving either behind means the bill is not zero.

Resume takes about 15 minutes, most of it the Docker build.

### B. Keep a snapshot — about $0.25/month

```
Instance → Snapshots → Create snapshot     (wait for it to finish)
Instance → Manage → Delete
```

Not free, but resume is 5 minutes instead of 15 and the ingested documents come
back with it.

---

## Resuming

### From nothing (after option A)

Create a $12 Ubuntu 24.04 instance, open port 80, then:

```bash
sudo apt-get update -qq && sudo apt-get install -y -qq git
git clone https://github.com/<you>/semantic-rag-search.git
cd semantic-rag-search
nano .env                     # GEMINI_API_KEY=...  LLM_PROVIDER=gemini
sudo bash deploy/setup.sh
bash deploy/seed.sh           # loads seed/*.txt back in
```

### From a snapshot (after option B)

```
Snapshots → the snapshot → Create new instance   (same $12 bundle)
```

Containers start on their own — every service is `restart: unless-stopped`, so
a fresh boot brings the stack back with no SSH needed. Check:

```bash
curl http://<new-ip>/api/health
```

---

## Confirming you are not being billed

The step people skip. A day after deleting:

```
Billing and Cost Management → Bills → expand "Lightsail"
```

Instance hours should have stopped at the deletion time, and there should be no
snapshot or static-IP line. `Cost Explorer` set to daily granularity shows the
same thing as a chart.

**The public IP changes each time.** Don't put a bare IP in the README as a
live demo link; it is dead most of the time. Keep screenshots there and share
the URL directly when it matters.

---

## Notes

**Rate limiting.** `/api/ask` is capped at 6 requests/minute per IP in
`web/nginx.conf`. It is the only endpoint that spends API quota, and an open
instance on the public internet is otherwise someone else's free tier.

**No key, no problem.** With `GEMINI_API_KEY` unset the retrieval half still
works — `/api/search` returns ranked passages without calling a model.

**Data.** Postgres and Mongo write to named Docker volumes, which live on the
instance disk and are therefore captured by the snapshot. `down -v` wipes them;
`down` does not.

**Two dates worth a calendar reminder.** The free account plan ends six months
after signup — upgrade to the paid plan before then or the remaining credits
are lost. The credits themselves expire twelve months after signup. Joining an
AWS Organization expires them immediately.

---

## Commands

```bash
cd ~/semantic-rag-search

docker compose -f docker-compose.yaml ps
docker compose -f docker-compose.yaml logs -f python-service
docker compose -f docker-compose.yaml restart node-api
docker compose -f docker-compose.yaml down            # stop, keep data
docker compose -f docker-compose.yaml up -d --build   # after a git pull
```

The `-f docker-compose.yaml` matters: without it Compose also loads
`docker-compose.override.yaml`, which publishes the database ports for local
development. On a public instance that is not wanted.
