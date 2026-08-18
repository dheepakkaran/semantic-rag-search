# Chapter 26 — Deploying to AWS

**Files:** `deploy/setup.sh`, `deploy/RUNBOOK.md`, `deploy/seed.sh`

## The target

One virtual machine running Docker Compose. No Kubernetes, no managed databases,
no load balancer.

That sounds like a step backwards after Part VIII. It is the right choice, and
for a reason worth stating:

**Everything this system needs fits on one box, and one box is one thing to
understand.** Five containers, two of them databases, on a machine with 2 GB of
memory. Splitting that across managed services would add a bill and several
consoles in exchange for scaling nobody needs.

Part VIII was still worth doing — it found three bugs that this deployment
benefits from. But needing Kubernetes and learning from Kubernetes are different
things.

## Choosing the instance

AWS Lightsail rather than EC2. The difference is packaging:

| | Lightsail | EC2 |
|---|---|---|
| Price | Flat, disk and transfer included | Instance + EBS + IPv4, itemised |
| Setup | Pick a size, pick an OS | VPC, subnet, security group, key pair |
| 2 GB plan | **$12/month** | ~$15 + ~$2.40 disk |

Lightsail is EC2 underneath with the choices already made. For a single box that
is a feature.

**The 2 GB plan, not 1 GB.** The 1 GB plan is $7 and will not build the Python
image — Chapter 20's 5.42 GB pip layer needs more memory than that during
installation.

## Before touching anything: a budget

```
Billing and Cost Management → Budgets → Create budget
  Template : Zero spend budget
  Amount   : $0.01
  Email    : you
```

First, before any resource exists.

A zero-spend budget emails the moment anything at all is charged. On a free plan
that should never fire, which is exactly why it is useful: if it does, something
is running that you did not intend.

It is also one of the onboarding tasks AWS pays $20 of credit for, so the safety
net is free and then some.

## Creating it

```
Platform   : Linux operating system   ← not "Linux apps"
Blueprint  : Ubuntu 24.04 LTS
Plan type  : General purpose
Network    : Dual-stack               ← needs a public IPv4
Size       : $12  (2 GB, 2 vCPU, 60 GB SSD, 3 TB transfer)
Name       : semantic-rag-search
Snapshots  : off
```

Two of those are easy to get wrong.

**"Linux operating system", not "Linux apps".** The apps list offers WordPress,
LAMP, Node.js and others with software pre-installed. We want a clean Ubuntu;
Docker brings everything else.

**Dual-stack, not IPv6-only.** The IPv6-only plans are cheaper. Without a public
IPv4 address most people cannot reach the site at all.

Two minutes later:

```
Instance status   Running
Public IPv4       32.199.156.62
```

## Opening one port

```
Networking → IPv4 Firewall → Add rule
  Application : HTTP
  Protocol    : TCP
  Port        : 80
```

Only 80, plus the SSH rule that already exists. Nothing else needs to be
reachable — which is exactly the arrangement Chapter 21's compose file was built
for, where only the web container publishes a port.

## The deployment

Three commands in the browser SSH window.

```bash
sudo apt-get update -qq && sudo apt-get install -y -qq git \
  && git clone https://github.com/<you>/semantic-rag-search.git \
  && cd semantic-rag-search
```

```bash
cp .env.example .env && nano .env
```

```
LLM_PROVIDER_CHAIN=gemini,openai
GEMINI_API_KEY=...
OPENAI_API_KEY=...
WEB_PORT=80
```

```bash
sudo bash deploy/setup.sh
```

## What the script does

```bash
# Safe to run twice: every step checks whether it has already been done. That
# matters because this is the script you run again after recreating the
# instance from a snapshot.
```

Idempotence is the design requirement, because Chapter 27 deletes this instance
and rebuilds it.

**Swap first.**

```bash
if [[ $(swapon --show --noheadings | wc -l) -gt 0 ]]; then
  log "swap already present, skipping"
else
  log "adding ${SWAP_SIZE} swap"
  fallocate -l "$SWAP_SIZE" "$SWAP_FILE" || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=2048
  ...
fi
```

```bash
# The python-service image installs torch, which is ~500 MB and peaks well
# above what a 2 GB instance has spare. Without swap the build is killed.
```

This is Chapter 20's image size arriving as an operational constraint. Without
swap, `pip install` on a 2 GB box is killed by the OOM reaper partway through,
with an error that does not mention memory.

**Docker from its own repository**, not Ubuntu's — the packaged version lags and
the Compose plugin is separate.

**Then a check, not a guess:**

```bash
if ! grep -qE '^GEMINI_API_KEY=.+' .env; then
  cat <<'MSG'
  .env has no GEMINI_API_KEY yet. Add it before starting:
      nano .env
  Then run this script again. Search still works without a key; only the
  grounded-answer endpoint needs one.
MSG
  die "GEMINI_API_KEY is not set in .env"
fi
```

Failing here, with instructions, beats building for ten minutes and then failing
to answer a question.

**Finally:**

```bash
# -f names the base file explicitly, which skips docker-compose.override.yaml
# and its development-only published ports.
docker compose -f docker-compose.yaml up -d --build
```

Chapter 21's override mechanism, doing its job: the deploy command is the safe
one by default.

## What it looks like

```
==> adding 2G swap
==> installing docker
==> building and starting (first build takes 5-10 minutes)
```

Then a long quiet stretch — PyTorch — and:

```
✓ Image mongo:7                        Pulled     14.9s
✓ Image postgres:16-alpine             Pulled      9.2s
✓ Image semantic-rag-search-node-api   Built     540.5s
✓ Image semantic-rag-search-web        Built     540.5s
✓ Image semantic-rag-search-python-service Built 540.4s
✓ Container ...-mongo-1                Healthy     8.3s
✓ Container ...-postgres-1             Healthy     9.0s
✓ Container ...-python-service-1       Started     8.2s
✓ Container ...-node-api-1             Started     8.8s
✓ Container ...-web-1                  Started     9.0s

==> waiting for the stack to report healthy
==> done

  Open:  http://32.199.156.62
```

About fifteen minutes, nine of them building.

## The empty system

Opening it gives:

```
No documents have been ingested yet.
There are no notes to search yet — add some from the Notes panel.
```

Which is correct — a new server has an empty database — and is Chapter 15's
two-message empty state earning its place. The generic *"nothing came close"*
would have looked like a broken search on a fresh install.

```bash
bash deploy/seed.sh
```

```
==> ingesting: Lectures 3-5 Training Overfitting Embeddings
    5 chunks stored (id 1)
==> done — 1 document(s) in the store
```

The notes live in `seed/` in the repository, which is what makes the server
disposable — Chapter 27 depends on it.

## Live

```
Q: overfitting

Overfitting occurs when a model has learned the noise in its training
examples rather than the pattern behind them [2]. A model that has
memorised its training set can score perfectly on that set and still be
useless on anything new [2, 3]...

answered by gemini-3.6-flash

GROUNDED ON
Lectures 3-5 — Training, Overfitting, Embeddings    ▬▬▭▭▭  0.391
```

On a public IP, with citations, on hardware costing $0.0164 an hour.

## Two things that went wrong

> **`WEB_PORT` was missing**
>
> The `.env` was filled in from `.env.example`, which does not include
> `WEB_PORT`. So Compose used its default of 8080 — while the firewall allowed
> only 80.
>
> Nothing was broken. The stack was healthy, the containers were up, and the
> site was unreachable. That combination is the hardest kind to diagnose because
> every diagnostic says "fine".
>
> `setup.sh` now guarantees it:
>
> ```bash
> grep -q '^WEB_PORT=' .env || echo "WEB_PORT=80" >> .env
> ```
>
> **A default that is right for development is a trap in production unless
> something enforces the production value.**

> **The IP changes when you stop the instance**
>
> Lightsail's own note:
>
> > *Public IPv4 addresses are used to connect to your instance over the public
> > internet. Your public IPv4 address changes when you stop and start your
> > instance unless you attach a static IPv4 address.*
>
> Which matters directly for Chapter 27, where the instance is deleted and
> recreated. A static IP would fix it — and a static IP that is *not attached to
> a running instance* is billed by the hour, so for a machine that spends most
> of its life deleted, the changing address is cheaper.
>
> The consequence is that the README carries screenshots, not a live link.

## Why a README screenshot beats a live link

A deployed demo on a free tier is asleep, deleted, or out of quota most of the
time. A recruiter who clicks a dead link learns the wrong thing.

Screenshots always work. The live URL goes in a message when it matters, after
bringing the instance up.

That is not defeatism about hosting. It is the same reasoning as the rest of this
book: **be honest about what actually works, rather than optimistic about what
should.**

---

## What you should take from this chapter

| | |
|---|---|
| One box | Everything fits; one box is one thing to understand |
| The 2 GB plan | The 1 GB plan cannot build the image |
| Budget first | Before any resource exists |
| Idempotent script | Because Chapter 27 deletes and rebuilds this |
| Swap | Chapter 20's image size, as an operational constraint |
| The healthy-but-unreachable bug | `WEB_PORT` defaulted to 8080; the firewall allowed 80 |
| Screenshots, not a live link | The link is asleep most of the time |

---

**Next:** [Chapter 27 — Paying for it](27-cost.md), the last chapter, about
turning it off.
