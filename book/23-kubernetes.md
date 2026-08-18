# Chapter 23 — Kubernetes manifests

**Files:** `k8s/00-config.yaml` … `k8s/40-web.yaml`

## Why bother, honestly

This system runs fine under Compose on one machine. Kubernetes adds a control
plane, five more files and a new vocabulary to solve problems — scheduling across
nodes, rolling updates, self-healing — that a single-instance demo does not have.

So the honest reason is not "it needed it". It is:

**Kubernetes is where the containers from Part VII meet an environment that is
not Docker Compose.** Everything that was implicitly true — the network, the DNS
server, the image store, the startup ordering — becomes explicit and different.
Chapter 24 is three bugs that only exist because of that, and none of them could
have been found on Compose.

That is a real reason to do it, and it is more useful than pretending a notes app
needs orchestration.

## The vocabulary, briefly

| Compose | Kubernetes | |
|---|---|---|
| a service | **Deployment** | what to run, and how many copies |
| a service name | **Service** | a stable name and address for those copies |
| `environment:` | **ConfigMap** | non-secret settings |
| values from `.env` | **Secret** | API keys |
| `depends_on` | *(nothing)* | ordering is not expressed; containers retry |
| `healthcheck` | **probes** | liveness and readiness, and they differ |

That fifth row is the one that changes how you write things. Compose can wait for
PostgreSQL to be healthy before starting the Node service. Kubernetes has no
equivalent — the scheduler starts everything and expects each container to cope
with its dependencies being absent.

Which is why Chapter 21's `restart: unless-stopped` mattered: on Kubernetes the
equivalent behaviour is the default, and the idiom is **crash and be restarted**
rather than **wait and retry**.

## What was written

```
k8s/
├── 00-config.yaml          ConfigMap
├── 10-databases.yaml       postgres + mongo (Deployment + Service each)
├── 20-python-service.yaml  Deployment + Service
├── 30-node-api.yaml        Deployment + Service
└── 40-web.yaml             Deployment + Service (NodePort)
```

```
1 ConfigMap · 5 Deployments · 5 Services
```

Numbered prefixes because `kubectl apply -f k8s/` applies in filename order, and
config should exist before anything referencing it.

## A Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: python-service
spec:
  replicas: 1
  selector:
    matchLabels: { app: python-service }
  template:
    metadata:
      labels: { app: python-service }
    spec:
      containers:
        - name: python-service
          image: semantic-rag-search-python-service:latest
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8000
          env:
            - name: MONGO_URI
              valueFrom:
                configMapKeyRef: { name: rag-config, key: MONGO_URI }
            - name: GEMINI_API_KEY
              valueFrom:
                secretKeyRef: { name: rag-secrets, key: GEMINI_API_KEY }
          resources:
            requests: { memory: 512Mi, cpu: 250m }
            limits:   { memory: 1536Mi, cpu: "1" }
```

`imagePullPolicy: IfNotPresent` is doing real work here. The default for a
`:latest` tag is `Always` — Kubernetes would try to pull from a registry and fail,
because this image was built locally and never pushed anywhere. `IfNotPresent`
says use the local one.

`requests` versus `limits`:

- **requests** — what the scheduler reserves. Used to decide which node has room
- **limits** — the hard ceiling. Exceed the memory limit and the container is
  killed

512 Mi requested and 1536 Mi allowed for the Python service, because the
embedding model needs a few hundred megabytes and generation is bursty. Getting
the limit too low produces an `OOMKilled` pod that restarts forever with no
obvious cause.

## Probes, and why there are two

```yaml
          livenessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 20
            periodSeconds: 20
          readinessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 10
            periodSeconds: 5
```

Same URL, different questions:

| Probe | Question | On failure |
|---|---|---|
| **liveness** | Is this process wedged? | Kill and restart it |
| **readiness** | Can it serve traffic *right now*? | Stop sending it requests |

The difference matters at startup. The Python service takes several seconds to
load the embedding model. During that window it is alive — restarting it would be
actively harmful, and would loop forever — but not ready.

Readiness handles that: the pod is excluded from the Service's endpoints until
`/health` answers, so no request arrives during model loading.

The comment says so:

```yaml
          # Liveness restarts a wedged container; readiness keeps traffic away
          # until the embedding model has finished loading, which takes a few
          # seconds after start.
```

Setting `initialDelaySeconds` too low on the liveness probe is a classic mistake:
the container is killed mid-startup, restarts, is killed again, and the pod sits
in `CrashLoopBackOff` while the application code is perfectly fine.

## Services

```yaml
apiVersion: v1
kind: Service
metadata:
  name: python-service
spec:
  selector: { app: python-service }
  ports:
    - port: 8000
      targetPort: 8000
```

A Service gives a stable name and virtual IP in front of whichever pods match the
selector. Pods are ephemeral — restarted, rescheduled, given new addresses. The
Service name is not.

That is why `RAG_SERVICE_URL: http://python-service:8000` works even though the
pod behind it may have been replaced twice.

It is also, exactly, Chapter 22's bug in a new setting: a name that resolves to
an address that changes. Kubernetes is *more* dynamic than Compose here, which is
why Chapter 24's version of the bug is worse.

## Reaching it from outside

```yaml
# NodePort rather than LoadBalancer: minikube has no cloud load balancer to
# hand out.
apiVersion: v1
kind: Service
metadata:
  name: web
spec:
  type: NodePort
  selector: { app: web }
  ports:
    - port: 80
      targetPort: 80
      nodePort: 30080
```

Three Service types matter:

| Type | Reachable from | Used here |
|---|---|---|
| `ClusterIP` (default) | inside the cluster only | the four internal services |
| `NodePort` | a port on the node's IP | **web** |
| `LoadBalancer` | a cloud load balancer | needs a cloud provider |

`LoadBalancer` is what you would use on a real cluster. On Docker Desktop or
minikube it stays `Pending` forever, because nothing exists to provision one.
`NodePort` publishes on `localhost:30080` and works everywhere.

## The Secret footgun

The original `00-config.yaml` contained both the ConfigMap and a Secret:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: rag-secrets
stringData:
  GEMINI_API_KEY: ""     # ← a placeholder, so `kubectl apply -f k8s/` works
```

The intention was reasonable: the directory should apply cleanly on a fresh
cluster, so every referenced object should exist.

The consequence was not.

> **What went wrong**
>
> The real secret was created first:
>
> ```bash
> kubectl create secret generic rag-secrets \
>   --from-literal=GEMINI_API_KEY="$GEMINI_API_KEY" \
>   --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
> ```
>
> ```
> GEMINI_API_KEY: 53 chars
> OPENAI_API_KEY: 164 chars
> ```
>
> Then `kubectl apply -f k8s/` would have applied the placeholder over it,
> replacing both keys with empty strings — and the failure would have surfaced
> minutes later as an unrelated-looking `503 GEMINI_API_KEY is not set`.
>
> Worse, it would happen on **every** apply. Every redeploy would silently wipe
> the credentials.

The fix was to delete the placeholder entirely and put the instructions in the
file's header, where the person running `apply` will read them:

```yaml
# The API keys are deliberately NOT here. An empty placeholder Secret in this
# file would be applied along with everything else and would silently wipe the
# real keys on every `kubectl apply -f k8s/`. Create them once instead:
#
#   set -a; . ./.env; set +a
#   kubectl create secret generic rag-secrets \
#     --from-literal=GEMINI_API_KEY="$GEMINI_API_KEY" \
#     --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
```

> **A placeholder that overwrites real data is worse than a missing file.** A
> missing Secret fails loudly at apply time, with a message naming what is
> absent. A placeholder succeeds, and breaks something else later.

## Databases with a deliberate weakness

```yaml
# Deployment, not StatefulSet: these use emptyDir, so data is lost when a pod
# restarts. That is deliberate for a single-node demo cluster — a real
# deployment wants a StatefulSet with a PersistentVolumeClaim, which needs a
# storage class this manifest cannot assume exists.
      volumes:
        - name: data
          emptyDir: {}
```

`emptyDir` lives and dies with the pod. Restart PostgreSQL and the documents are
gone.

That is wrong for production and right for this manifest, because a
`PersistentVolumeClaim` needs a `StorageClass`, and which one exists depends
entirely on the cluster. A manifest that assumes one is a manifest that fails on
someone else's cluster.

Stating the limitation in the file is better than shipping something that only
works on the author's laptop while looking production-ready.

## Applying it

```bash
kubectl apply -f k8s/
```

```
configmap/rag-config created
deployment.apps/postgres created
service/postgres created
deployment.apps/mongo created
service/mongo created
deployment.apps/python-service created
service/python-service created
deployment.apps/node-api created
service/node-api created
deployment.apps/web created
service/web created
```

Eleven objects. Then:

```bash
kubectl get pods
```

```
NAME                              READY   STATUS    RESTARTS      AGE
mongo-7ccbf97f56-t2qvc            1/1     Running   0             56s
node-api-547f65995d-6k8jh         1/1     Running   2 (53s ago)   56s
node-api-547f65995d-cxfp7         1/1     Running   2 (53s ago)   56s
postgres-79df7dd8d5-t55xg         1/1     Running   0             56s
python-service-78b5d879c5-2m2gf   1/1     Running   0             56s
web-66b796b5d-kfjrt               1/1     Running   0             56s
web-66b796b5d-ngnc7               1/1     Running   0             56s
```

Seven pods running. Note `node-api` shows `RESTARTS 2` — it started before
PostgreSQL was accepting connections, crashed, and was restarted until it worked.

That is not a bug. It is the model. There is no `depends_on`; the container is
expected to fail and be retried, and the restart count is the visible evidence of
it having done so.

## And then it did not work

```bash
curl localhost:30080/api/health
```

```
HTTP 000
```

Nothing. Seven healthy pods, and the site unreachable.

That is Chapter 24.

---

## What you should take from this chapter

| | |
|---|---|
| Why do it at all | It is where the containers meet a non-Compose environment |
| No `depends_on` | Crash and be restarted, rather than wait and retry |
| Two probes | Liveness restarts; readiness holds traffic during startup |
| `IfNotPresent` | Or Kubernetes tries to pull an image you never pushed |
| The footgun | A placeholder Secret silently wipes real keys on every apply |
| `emptyDir` | Deliberate, and documented, because a PVC assumes a StorageClass |

---

**Next:** [Chapter 24 — Three portability bugs](24-portability.md), the reason
this chapter was worth doing.
