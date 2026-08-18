# Chapter 24 — Three portability bugs

The containers from Part VII worked. Compose ran them, the tests passed, the site
answered questions.

Then the same images were applied to a Kubernetes cluster and three separate
things broke — each one an assumption that had been true under Compose and was
never written down, because nothing had ever contradicted it.

This chapter is the reason Chapter 23 was worth doing.

## Bug 1 — the image name

Before anything ran, every pod would have sat in `ImagePullBackOff`.

```yaml
image: semantic-rag-search/python-service:latest
```

```bash
docker images --format '{{.Repository}}' | grep semantic
```

```
semantic-rag-search-node-api
semantic-rag-search-python-service
semantic-rag-search-web
```

A **slash** in the manifest, a **hyphen** in reality.

Compose names images `<project>-<service>`, with the project taken from the
directory. The manifests were written by hand with a slash, which reads like an
organisation prefix and is what you would push to a registry.

Neither is wrong. They simply did not match, and nothing checks that a manifest
names an image that exists until a pod tries to start.

```bash
sed -i '' 's|image: semantic-rag-search/|image: semantic-rag-search-|' k8s/*.yaml
```

Then verify rather than assume:

```bash
for img in $(grep -h "image: semantic" k8s/*.yaml | awk '{print $2}'); do
  docker image inspect "$img" >/dev/null 2>&1 && echo "✅ $img" || echo "❌ $img missing"
done
```

```
✅ semantic-rag-search-python-service:latest
✅ semantic-rag-search-web:latest
✅ semantic-rag-search-node-api:latest
```

Small, and worth the space because of the class it belongs to: **a string in one
file that has to match a string produced by a different tool, with nothing
connecting them.** Those never fail at write time.

## Bug 2 — a resolver that does not exist

Seven pods running. `curl localhost:30080/api/health` returned nothing.

```bash
kubectl logs -l app=web --tail=8
```

```
[error] 37#37: recv() failed (111: Connection refused) while resolving,
resolver: 127.0.0.11:53
```

`127.0.0.11` is **Docker's embedded DNS server**. It exists inside a Docker
network. It does not exist in a Kubernetes pod — Kubernetes runs CoreDNS, on a
different address entirely:

```bash
kubectl get svc -n kube-system kube-dns
```

```
kube-dns   ClusterIP   10.96.0.10   53/UDP,53/TCP,9153/TCP
```

Chapter 22's fix had hardcoded the platform:

```nginx
resolver 127.0.0.11 valid=10s ipv6=off;
```

That line fixed a real bug on Compose and created a new one everywhere else.

### The fix: ask the container

The container already knows its own resolver — it is in `/etc/resolv.conf`, which
whatever platform is running it wrote correctly. So read it at start-up rather
than guessing.

The official nginx image runs every executable script in `/docker-entrypoint.d/`
before starting nginx, which is exactly the hook needed:

```sh
#!/bin/sh
# nginx resolves a proxy_pass hostname once at startup and caches the address
# forever unless a resolver is configured, so a redeployed backend is never
# picked up. But the resolver's own address is platform-specific: Docker's
# embedded DNS sits at 127.0.0.11, Kubernetes runs CoreDNS somewhere else.
# Hardcoding either one breaks the other.
set -e

resolver=$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf)
resolver=${resolver:-127.0.0.11}

echo "resolver: ${resolver} (from /etc/resolv.conf)"
sed -i "s|__RESOLVER__|${resolver}|g" /etc/nginx/conf.d/default.conf
```

And the config carries a placeholder:

```nginx
resolver __RESOLVER__ valid=10s ipv6=off;
```

On Kubernetes:

```
resolver: 10.96.0.10 (from /etc/resolv.conf)
```

Correct, without being told.

## Bug 3 — the one nobody expects

DNS fixed, and the site still failed:

```
502 Bad Gateway
```

```bash
kubectl logs -l app=web --tail=5
```

```
[error] 32#32: *27 node-api could not be resolved (3: Host not found)
```

Not "connection refused" this time. **Host not found.** The resolver was reached
and answered: no such name.

But other pods resolve it perfectly:

```bash
kubectl exec deploy/python-service -- python -c "
import urllib.request
print(urllib.request.urlopen('http://node-api:3001/api/health', timeout=5).read())"
```

```
b'{"status":"ok"}'
```

The same name, from a pod on the same cluster, works.

### Why

A normal DNS lookup uses the **search domains** in `/etc/resolv.conf`:

```
nameserver 10.96.0.10
search default.svc.cluster.local svc.cluster.local cluster.local
```

Ask for `node-api` and the resolver library tries `node-api.default.svc.cluster.local`
first. That is how every other pod finds it.

**nginx's `resolver` does not do this.** It queries the name exactly as written,
with no suffixes. `node-api` is not a fully-qualified name, so the answer is
NXDOMAIN — correctly.

Under Compose it worked because Docker's embedded DNS resolves the short service
name directly. There were no search domains involved, so the difference never
showed.

### The fix

The fully-qualified name is correct on Kubernetes and wrong on Compose, so it
cannot be hardcoded either. It becomes another start-up substitution, with the
platform supplying the value:

```sh
upstream=${NODE_API_UPSTREAM:-http://node-api:3001}

sed -i "s|__RESOLVER__|${resolver}|g; s|__UPSTREAM__|${upstream}|g" \
  /etc/nginx/conf.d/default.conf
```

```yaml
          env:
            # nginx's resolver queries this name verbatim — it does not apply
            # the search domains from resolv.conf — so it has to be the fully
            # qualified service name here. Under Compose the short name works
            # and the image's default is used instead.
            - name: NODE_API_UPSTREAM
              value: http://node-api.default.svc.cluster.local:3001
```

## One image, both platforms

The same image, started twice:

```
Compose      resolver: 127.0.0.11   upstream: http://node-api:3001
Kubernetes   resolver: 10.96.0.10   upstream: http://node-api.default.svc.cluster.local:3001
```

```bash
curl localhost:8080/api/health    # Compose
{"status":"ok"} (HTTP 200)

curl localhost:30080/api/health   # Kubernetes
{"status":"ok"} (HTTP 200)
```

Both platforms, one image, no branching in the config — the container discovers
one value and is told the other.

That split is the right one. **The resolver is discoverable, so discover it. The
upstream name is a deployment decision, so let the deployment say it.** Guessing
either would have produced a third bug on the next platform.

## What these three have in common

None of them is a mistake in the usual sense. Each was a **correct fix for one
environment, applied where its assumption was false.**

| Bug | The assumption | Where it held |
|---|---|---|
| Image name | Images are named `project/service` | Nowhere — it was written by hand |
| `127.0.0.11` | DNS is at Docker's embedded address | Compose only |
| Short hostname | The resolver applies search domains | Compose only |

Bugs 2 and 3 are the same shape: **a default that differs between platforms and
is invisible until you leave the first one.**

This is the same lesson as Chapter 7's `pythonpath`, where a test suite passed
locally and would have failed in CI because `python -m pytest` adds the current
directory to the path and `pytest` does not. Different layer, identical
mechanism.

> **The way to find these is not to think harder. It is to run the thing
> somewhere else.**

## What it cost, and what it bought

Roughly an hour, three fixes, and one script.

What it bought was not a Kubernetes deployment — nothing needs one. It was
finding three assumptions that were invisible under Compose and would have
surfaced later on some other platform, at a worse moment.

The AWS deployment in Chapter 26 runs Compose on one instance. It benefits from
all three fixes anyway: the image names are consistent, the resolver is
discovered rather than assumed, and the upstream is configuration rather than a
constant. That deployment went cleanly, and part of the reason is that Kubernetes
had already found the rough edges.

---

## What you should take from this chapter

| | |
|---|---|
| Bug 1 | A hand-written string that must match a tool's output — verify it |
| Bug 2 | `127.0.0.11` is Docker's DNS and exists nowhere else |
| Bug 3 | nginx's resolver ignores search domains; short names fail on Kubernetes |
| The pattern | Correct fixes carrying an unstated assumption about their platform |
| Discover vs configure | The resolver is discoverable; the upstream is a decision |
| The method | Run it somewhere else — thinking harder does not find these |

---

**Next:** [Chapter 25 — Continuous integration](25-ci.md), where the tests start
running without being asked.
