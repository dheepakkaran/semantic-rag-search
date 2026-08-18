# Chapter 27 — Paying for it

**File:** `deploy/RUNBOOK.md`

## The actual bill

```
$12 / month  ÷  730 hours  =  $0.0164 per hour
```

That is the whole cost model. Everything else is arithmetic on it.

The AWS free plan supplies $100 in credits, rising to $200 after five onboarding
tasks — one of which is creating the budget alert from Chapter 26, so the safety
net pays for itself.

Six months of continuous running is $72. The credits cover it, and cover the
interview season that motivated the project.

## The trap

Here is the thing that costs people money, in one line from AWS's own
documentation:

> Lightsail instances are charged **only when they're in the running or stopped
> state**.

Read it twice. **Stopped instances are still billed.**

The reasoning is defensible: the disk still exists, the plan still reserves the
resources, the instance can restart in seconds. But the mental model most people
carry — stopped means free — is wrong here, and it is a $12/month wrong.

EC2 behaves differently. A stopped EC2 instance costs nothing for compute; you
pay only for the EBS volume, a few dollars a month. Two AWS products, opposite
behaviours, same word.

| | Running | Stopped | Deleted |
|---|---|---|---|
| **Lightsail** | $12/mo | **$12/mo** | $0 |
| **EC2** | ~$15/mo | ~$2.40/mo (disk) | $0 |

So on Lightsail there is exactly one way to stop paying: **delete it.**

## Which is fine, because the server holds nothing

This is where a decision from Chapter 26 pays off.

```
code       →  GitHub
documents  →  seed/ in the repository
keys       →  .env, recreated from your password manager
built images →  rebuilt by setup.sh
```

Nothing on that instance is irreplaceable. Deleting it destroys a copy.

That is not luck. It is what `deploy/setup.sh` and `deploy/seed.sh` are *for* —
they exist so the answer to "how do I stop paying?" is `Delete`, rather than a
migration.

## The two ways to pause

### Keep a snapshot — about $0.25/month

```
Instance → Snapshots → Create snapshot   (wait for it to finish)
Instance → Manage → Delete
```

A snapshot is billed on data actually written, not disk size. This instance uses
roughly 5 GB — the OS, the built images, a little data — so at $0.05/GB/month
that is about **$0.25**.

Restoring is a few clicks and about five minutes. Everything comes back: the
built images, the ingested documents, the configuration.

### Delete everything — $0.00

```
Instance    → Manage → Delete
Snapshots   → delete any snapshots
Networking  → release any static IP that is not attached
```

All three, or the bill is not zero. A forgotten snapshot is $0.25/month forever;
an unattached static IP is billed by the hour.

Restoring means running Chapter 26 again: create an instance, clone, `.env`,
`setup.sh`, `seed.sh`. About fifteen minutes, most of it the image build.

## The arithmetic for one real pattern

Two months off, one week on:

| | | |
|---|---|---|
| One week running | 168 h × $0.0164 | **$2.76** |
| Two months as a snapshot | 5 GB × $0.05 × 2 | **$0.50** |
| **Total** | | **≈ $3.30** |

Against the alternative of leaving it stopped:

| | | |
|---|---|---|
| Two months stopped | 2 × $12 | $24.00 |
| One week running | | $2.76 |
| **Total** | | **$26.80** |

**$3.30 against $26.80**, for identical availability. The difference is entirely
the word *deleted* versus *stopped*.

At $200 of credit, the first pattern gives about sixty of those cycles.

## The two clocks on AWS credits

```
6 months   the free plan ends
12 months  the credits expire
```

These are different, and mixing them up loses money.

At six months the free plan ends. AWS's wording:

> After the 6 month free period or when all credits are used, you can choose to
> upgrade to a paid plan. Otherwise, **your account closes automatically**.

At twelve months the credits themselves expire, regardless.

So:

| At month 6 you… | Remaining credits |
|---|---|
| Upgrade to the paid plan | **Survive** until month 12 and apply to bills |
| Do nothing | **Lost** — the account closes |

The catch in upgrading: on the paid plan, when the credits run out you are
charged. That is exactly when the Chapter 26 budget alert stops being a formality.

Two calendar reminders are worth setting on the day you create the account:

```
month 5   "AWS free plan ends soon — upgrade, or export and let it close"
month 11  "AWS credits expire next month"
```

## One thing that voids it all

From the AWS FAQ:

> If you join an AWS Organization or set up an AWS Control Tower landing zone,
> your Free Tier credits **expire immediately**.

Worth knowing if you are a student. University AWS programmes often work by
inviting your account into an organisation — and doing that with a personal
account holding $200 of credit destroys the credit instantly.

Keep them separate.

## The other quota

The cloud bill is not the only budget.

```
Gemini free tier: 20 generations per day
```

Twenty. An afternoon of testing consumes it, which is exactly what happened while
building this system and is why Chapter 17 exists.

Two things follow, and both are already in the design:

**`/search` costs nothing.** It never calls a model. When the quota is gone,
retrieval still works and the system is degraded rather than down.

**The fallback chain has a paid provider on it.** OpenAI charges per token, and
`gpt-4o-mini` is cheap enough that a few dollars of credit covers thousands of
questions. But it is not free, and pointing a fallback chain at a paid provider
under real load is a decision, not a default.

## The habit worth keeping

Deleting the instance is a two-minute operation, and it is worth doing the moment
you stop needing it rather than "later this week".

The failure mode is not dramatic. Nobody gets a shocking bill from one $12
instance. What happens is quieter: it runs for four months, quietly consuming
credits that were meant to last a year, and the money is gone when you actually
need it.

**Turning things off is a skill, and it is the one part of cloud engineering that
nobody demonstrates in a tutorial.**

## Confirming it worked

The step people skip. A day after deleting:

```
Billing and Cost Management → Bills → expand "Lightsail"
```

Instance hours should stop at the deletion time, with no snapshot line and no
static-IP line.

A budget alert tells you when something *is* charging. Reading the bill tells you
that nothing is. They are different checks, and the second one takes thirty
seconds.

---

## What you should take from this chapter

| | |
|---|---|
| The trap | Lightsail bills **stopped** instances. Only deleting stops it |
| Why deleting is fine | The server holds nothing the repository does not |
| Snapshot | ~$0.25/month, restore in five minutes |
| Delete everything | $0.00, restore in fifteen |
| Real pattern | $3.30 against $26.80 for the same availability |
| Two clocks | Free plan at 6 months, credits at 12 — upgrade or lose them |
| The other quota | 20 generations a day; `/search` still works without any |

---

## The end of the walkthrough

That is the whole system: a folder, a search that understands what you mean, an
answer you can check, five containers, two orchestrators, a public address, and a
way to turn it off.

What is left is the appendices — [every bug in order](A-bugs.md), a
[command reference](B-commands.md), and a [glossary](C-glossary.md).
