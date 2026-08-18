# Appendix B — Command reference

Every command in this book, grouped by what you are trying to do. Copy-paste
ready.

---

## Local development

### Python service

```bash
cd python-service
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
```

Always `./venv/bin/python -m pip`, never `./venv/bin/pip` — see Appendix A #1.

```bash
# run the API
./venv/bin/python -m uvicorn app:app --reload --port 8000

# tests
./venv/bin/python -m pytest -q

# one test, with output
./venv/bin/python -m pytest tests/test_fallback.py -v -s
```

### The CLI — no server, no database, no key

```bash
cd python-service

./venv/bin/python cli.py sample_notes.txt search "what stops a model memorising?"

LLM_PROVIDER=mock ./venv/bin/python cli.py sample_notes.txt ask "why hold out a validation set?"
```

`search` never calls a model, so it works with no key and no quota.

### Node API

```bash
cd node-api
npm install
npm run dev            # tsx watch
npm test               # node --test
npm run build          # tsc
```

### Web

```bash
cd web
npm install
npm run dev            # vite, port 5173
npm run build          # tsc + vite build
```

### The benchmark

```bash
cd python-service && ./venv/bin/python ../deploy/bench.py
```

---

## Docker Compose

```bash
cp .env.example .env          # then add GEMINI_API_KEY
docker compose up --build
open http://localhost:8080
```

```bash
docker compose ps                        # what is running, and healthy?
docker compose logs -f python-service    # follow one service
docker compose logs --tail=50 web
docker compose restart node-api
docker compose down                      # stop, keep volumes
docker compose down -v                   # stop, delete data
```

### Rebuilding one service

```bash
docker compose build node-api
docker compose up -d node-api
```

### Inside a container

```bash
docker compose exec python-service sh
docker compose exec postgres psql -U rag -d rag -c '\dt'
docker compose exec mongo mongosh rag --eval 'db.chunks.countDocuments()'
```

### Which address a container has

The Chapter 22 debugging command:

```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  semantic-rag-search-node-api-1
```

### Image sizes

```bash
docker images | grep semantic-rag
docker history semantic-rag-search-python-service --human
```

---

## Kubernetes (minikube)

```bash
minikube start --memory=4096 --cpus=2
eval $(minikube docker-env)      # build into minikube's daemon, not your Mac's
docker compose build             # images now exist inside the cluster
```

The `eval` applies to that shell only. A new terminal needs it again.

```bash
kubectl create secret generic rag-secrets \
  --from-literal=GEMINI_API_KEY=your-key-here

kubectl apply -f k8s/
kubectl get pods -w              # watch them come up
minikube service web             # opens a browser at the NodePort
```

### Looking at what is wrong

```bash
kubectl get pods
kubectl describe pod <name>              # events at the bottom — read these first
kubectl logs <name>
kubectl logs <name> --previous           # a crashed container's last words
kubectl logs -l app=web --tail=50        # by label, across replicas
```

### Getting inside

```bash
kubectl exec -it <pod> -- sh
kubectl exec <pod> -- cat /etc/resolv.conf      # the Chapter 24 command
kubectl exec <pod> -- env | sort
```

### Port-forward without a NodePort

```bash
kubectl port-forward svc/web 8080:80
```

### Tearing down

```bash
kubectl delete -f k8s/
minikube stop
minikube delete                  # removes the VM and every built image
```

---

## AWS Lightsail

### On your Mac

```bash
chmod 400 ~/Downloads/LightsailDefaultKey-us-east-1.pem
ssh -i ~/Downloads/LightsailDefaultKey-us-east-1.pem ubuntu@<public-ip>
```

### On the instance, first time

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/<you>/semantic-rag-search.git
cd semantic-rag-search
cp .env.example .env
nano .env                        # add GEMINI_API_KEY, save with ctrl+O, exit ctrl+X
bash deploy/setup.sh
bash deploy/seed.sh
```

`setup.sh` installs Docker, adds swap, enforces `WEB_PORT=80`, and brings the
stack up. It is idempotent — run it again after a `git pull`.

### Updating a running instance

```bash
cd semantic-rag-search
git pull
docker compose up -d --build
```

### Checking on it

```bash
docker compose ps
free -h                          # is swap being used?
df -h                            # disk
docker stats --no-stream
curl -s localhost/api/search?q=test | head -c 200
```

---

## Testing the deployed system

### Health

```bash
curl -s http://<ip>/api/search?q=dropout | python3 -m json.tool | head -20
```

### An answer

```bash
curl -s -X POST http://<ip>/api/ask \
  -H 'content-type: application/json' \
  -d '{"question":"what stops a model memorising?"}' | python3 -m json.tool
```

### The rate limit (Chapter 18)

```bash
for i in $(seq 1 10); do
  printf "%s " "$(curl -s -o /dev/null -w '%{http_code}' \
    -X POST http://<ip>/api/ask \
    -H 'content-type: application/json' -d '{"question":"test"}')"
done; echo
```

Expect `200 200 200 200 429 429 …` against one instance.

---

## Git and CI

```bash
git add -A && git commit -m "message"
git push

gh run list --limit 5
gh run view <id>
gh run watch
```

---

## Emergencies

### Port already in use

```bash
lsof -i :8000
kill <pid>
```

### Docker will not start on macOS

Usually another user account is logged in with Docker Desktop running. Fast user
switching keeps their processes alive. Log that account out — you cannot kill
another user's processes without their password.

### The stack is up but the site is unreachable

Check the port the web container is actually published on against the firewall
rule. This is Appendix A #15.

```bash
docker compose ps               # look at the PORTS column
grep WEB_PORT .env
```

### A container keeps restarting

```bash
docker compose logs --tail=100 <service>
docker compose ps               # the STATUS column shows the restart count
```

### Out of memory during the image build

The Python image builds PyTorch and needs headroom. On a 2 GB instance, swap is
what makes it possible — `setup.sh` adds 2 GB of it. Without swap the build is
killed with no useful message.

---

## Stopping the bill

```
Instance → Snapshots → Create snapshot
Instance → Manage → Delete
Networking → release any unattached static IP
```

All three. See Chapter 27 — a stopped Lightsail instance still costs $12/month.
