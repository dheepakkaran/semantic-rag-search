# Chapter 22 — The nginx caching bug

**File:** `web/nginx.conf`

## How it started

Everything worked. Five containers up, the interface answering questions, the
rate limit firing correctly.

Then one container was rebuilt — just the Node service, after a small code
change:

```bash
docker compose -f docker-compose.yaml up -d --build node-api
```

```
Container semantic-rag-search-node-api-1  Started
```

And the site broke:

```html
<html>
<head><title>502 Bad Gateway</title></head>
<body>
<center><h1>502 Bad Gateway</h1></center>
<hr><center>nginx/1.27.5</center>
</body>
</html>
```

502 means nginx could not reach the thing behind it. But the thing behind it was
running, healthy, and had just been rebuilt on purpose.

## Narrowing it down

First: is the Node service actually alive?

```bash
docker compose -f docker-compose.yaml ps
```

```
node-api    Up 2 minutes
web         Up 7 minutes
```

Both up. Note the ages — `web` is older, which turns out to matter.

Second: can anything else reach it? Test from *inside* the web container, so the
path is the same one nginx uses:

```bash
docker compose exec -T web wget -qO- http://node-api:3001/api/health
```

```
{"status":"ok"}
```

**The Node service is reachable from the web container.** Its own nginx cannot
reach it, but a shell in the same container can.

That narrows it sharply. The network is fine. DNS is fine. The problem is inside
nginx.

## The evidence

```bash
docker inspect semantic-rag-search-node-api-1 \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

```
172.18.0.4
```

And nginx's error log:

```
connect() failed (111: Connection refused) while connecting to upstream,
client: 192.168.65.1, server: , request: "POST /api/ask HTTP/1.1",
upstream: "http://172.18.0.3:3001/api/ask"
```

```
node-api actually at :  172.18.0.4
nginx connecting to  :  172.18.0.3
```

nginx was talking to the address the container had **before** it was rebuilt.

## Why

nginx resolves a hostname in `proxy_pass` **once, at startup**, and caches the
result for the lifetime of the process.

```nginx
location /api/ {
    proxy_pass http://node-api:3001/api/;
}
```

At startup, `node-api` resolved to `172.18.0.3`. nginx recorded that and never
asked again.

Rebuilding the Node service destroys the container and creates a new one, which
gets whatever address Docker hands out next — `172.18.0.4`. The old address now
belongs to nothing.

nginx has no idea. It keeps dialling a number that has been disconnected.

## Why it is worse than a local annoyance

It is tempting to shrug: restart nginx and move on.

But look at when it happens. **It happens on every redeploy of the backend.**

Deploy a fix to the Node service in production and the site returns 502 until
someone notices and restarts the web container. The deployment "succeeded" — new
container running, health checks passing — and the site is down.

That is a production outage caused by a successful deployment, which is a
particularly bad kind.

## The fix

nginx *will* re-resolve, but only if two conditions are met: a `resolver` is
configured, and the upstream is in a **variable** rather than a literal.

```nginx
    resolver 127.0.0.11 valid=10s ipv6=off;
    set $node_api "http://node-api:3001";

    location /api/ {
        proxy_pass $node_api$request_uri;
    }
```

Three things changed.

**`resolver 127.0.0.11`** — Docker's embedded DNS server. Without a resolver
directive nginx has nothing to ask at runtime; it only uses the system resolver
during startup.

**`valid=10s`** — cache answers for ten seconds. A moved container is picked up
within ten seconds rather than never.

**`set $node_api ...` and `proxy_pass $node_api...`** — this is the part that is
genuinely surprising. A literal hostname in `proxy_pass` is resolved at startup
*even with a resolver configured*. Putting it in a variable forces runtime
resolution.

The change from a literal to a variable looks cosmetic and is the entire fix.

## Proving it

Rebuilding did not reproduce it reliably — Docker often reuses the same address
if it is free. So the address was taken deliberately.

```bash
NET=semantic-rag-search_default

docker compose stop node-api

# make something else take the freed address
docker run -d --rm --name ipsquatter --network "$NET" alpine sleep 120

docker compose start node-api
```

```
squatter took       : 172.18.0.4
node-api's new IP   : 172.18.0.7
```

The address moved by force. Now, **without touching the web container**:

```bash
for i in 1 2 3; do curl -s -w " HTTP %{code}" localhost:8080/api/health; sleep 5; done
```

```
5s:  {"status":"ok"} HTTP 200
10s: {"status":"ok"} HTTP 200
15s: {"status":"ok"} HTTP 200
```

`172.18.0.4` → `172.18.0.7`, and nginx followed on its own.

Before the fix this was a guaranteed 502. That is the difference between "I think
this is fixed" and "I made the failure happen and watched it not fail."

> **When you fix something intermittent, force the condition.** A fix confirmed
> only by "it stopped happening" is a fix you will be debugging again.

## The second half of this bug

This fix broke Kubernetes.

`127.0.0.11` is Docker's embedded DNS. It does not exist in a cluster — Kubernetes
runs CoreDNS somewhere else entirely. On the first `kubectl apply`:

```
recv() failed (111: Connection refused) while resolving,
resolver: 127.0.0.11:53
```

The fix for one platform was hardcoded to that platform. Chapter 24 covers that,
and the second surprise waiting behind it.

The final version takes the resolver from the container's own `/etc/resolv.conf`
at start-up, so it is correct on both:

```sh
resolver=$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf)
sed -i "s|__RESOLVER__|${resolver}|g" /etc/nginx/conf.d/default.conf
```

## Why this was not caught earlier

Worth asking, because the answer generalises.

Every test in this project — 51 of them — passes. None could have caught this:

- The Python tests never involve nginx
- The Node tests mock the HTTP layer entirely
- Neither builds a container

This bug only exists in the interaction between a running nginx and a container
lifecycle. It has no unit.

It also does not appear on a first deployment. Everything starts together,
addresses are fresh, and it works. It appears on the **second** deployment of one
service, which in development is exactly when you have stopped watching.

> **Some bugs live only in the composition.** A suite of unit tests can be green
> while the system is broken, and the only way to find these is to actually
> operate the thing: deploy it, redeploy it, restart pieces of it, and watch.

## What good came of it

The debugging path is worth keeping as a template:

1. **Is the target alive?** — `docker compose ps`
2. **Can anything reach it?** — `exec` into the *caller* and try
3. **Compare what should be with what is** — `docker inspect` against the error log
4. **Force the condition** — the squatter container
5. **Verify without touching the fixed thing** — web was never restarted

Step 2 is the one that cracked it. Testing from the host would have shown the
same 502 and taught nothing. Testing from *inside the calling container* split
"the network is broken" from "nginx is confused" in a single command.

---

## What you should take from this chapter

| | |
|---|---|
| The bug | nginx resolves `proxy_pass` hostnames once, at startup |
| Why it matters | Every backend redeploy causes it — a successful deploy takes the site down |
| The fix | A `resolver`, and the upstream in a **variable** |
| The surprise | A literal hostname is cached even with a resolver configured |
| Prove it | Force the address to move; verify without touching nginx |
| The lesson | Some bugs live only in the composition; only operating it finds them |

---

**Next:** [Chapter 23 — Kubernetes manifests](23-kubernetes.md), where the same
containers meet a real cluster.
