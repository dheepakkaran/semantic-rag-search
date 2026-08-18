# Appendix A — Every bug, in order

Fifteen problems, in the order they were hit. Each with the real symptom, the
cause, and the fix.

Read down the *cause* column and a pattern appears: most of these are not
mistakes in logic. They are assumptions that were true in one place and silently
false in another.

---

## 1. A moved virtual environment

**Chapter 2** · symptom:

```
./venv/bin/pip: bad interpreter:
  /old/path/venv/bin/python3: no such file or directory
```

**Cause.** A virtualenv hardcodes its absolute path into the scripts in `bin/`.
The project folder was reorganised and `venv/` moved with it.

**Fix.** Use `./venv/bin/python -m pip`, whose binary is a symlink and survives,
or delete and recreate. `venv/` is disposable.

---

## 2. `pytest` and `python -m pytest` are not the same

**Chapter 7** · symptom, in CI only:

```
ModuleNotFoundError: No module named 'rag'
```

**Cause.** `python -m` adds the current directory to `sys.path`. The launcher
script does not. Local runs used the first form; CI uses the second.

**Fix.** `pythonpath = .` in `pytest.ini`. Found by deliberately running the
suite the way CI would.

---

## 3. A retired model

**Chapter 9** · symptom, on the first real API call:

```
404 NOT_FOUND. This model models/gemini-2.5-flash is no longer available
to new users. Please update your code to use models/gemini-3.6-flash
```

**Cause.** The default model name was written from memory. The model had been
retired.

**Fix.** One word in `DEFAULT_MODELS`. The name was already in one place and
overridable by environment variable, which is what made it a one-word fix.

**Lesson.** Anything you "know" about a provider has a shelf life.

---

## 4. Markdown rendered as literal asterisks

**Chapter 8** · symptom, in the browser:

```
* **More data:** A larger, more varied training set makes memorisation
harder and helps the model find the underlying pattern [2].
```

**Cause.** The model returned markdown; the interface renders the answer as plain
text.

**Fix.** One line in the prompt: *"Write plain prose. Do not use markdown, bullet
points or asterisks."* Cheaper than adding a markdown renderer for one field.

**Lesson.** The prompt is part of the interface contract.

---

## 5. A quota error reported as a bug

**Chapter 10** · symptom:

```
Internal Server Error
```

…while the log said:

```
429 RESOURCE_EXHAUSTED. 'You exceeded your current quota... limit: 20,
 model: gemini-3.6-flash. Please retry in 34.476147438s'
```

**Cause.** `LLMError` propagated uncaught; FastAPI's default for an unhandled
exception is 500.

**Fix.** Catch it and pass the provider's status through. Two tests pin it.

**Lesson.** An error that crosses a boundary should keep its meaning.

---

## 6. An error inside an error

**Chapter 13** · symptom:

```json
{"error":"retrieval service failed",
 "detail":"{\"detail\":\"429 RESOURCE_EXHAUSTED. {'error': {'code': 429..."}
```

**Cause.** The Node service attached the Python service's whole response body —
already JSON — as the `detail` string of its own JSON error.

**Fix.** Parse and unwrap one level, with a `catch` for bodies that are not JSON.

**Lesson.** Every boundary an error crosses is a chance to lose information.

---

## 7. A variable shadowing the DOM

**Chapter 14** · symptom: none. Found by reading.

```typescript
{documents.map((document) => ( ... ))}
```

**Cause.** `document` is also the browser's global. Inside the callback it is a
database row.

**Fix.** Renamed to `doc`. Harmless today; a confusing runtime error the day
someone writes `document.querySelector` in that block.

---

## 8. An empty state that flashed

**Chapter 14** · symptom: *"Nothing added yet"* appeared for a moment on every
load, even with documents.

**Cause.** `documents` starts as `[]`, which was treated as "empty" rather than
"not yet known".

**Fix.** A `loaded` flag, and three states rather than two: unknown, empty,
populated.

---

## 9. A button that would have submitted

**Chapter 14** · symptom: none yet.

**Cause.** `<button>` defaults to `type="submit"`. This one is outside any form,
so it does nothing — until someone wraps that area in a form.

**Fix.** `type="button"`. Found by listing every button and its resolved type in
the console.

---

## 10. Three contrast failures

**Chapter 16** · symptom: none visible. Found by measuring.

```
#8a8a91  --muted           3.40:1   FAIL (needs 4.5)
#c9c9ce  placeholder       1.64:1   FAIL (needs 3.0)
#e4e4e6  input underline   1.26:1   FAIL (needs 3.0)
```

**Cause.** Colours chosen by eye, on a good screen, in good light.

**Fix.** `#74747d` (4.59:1), `#8a8a91` (3.40:1, large text), `#93939c` (3.02:1).
Decorative dividers left alone.

**Lesson.** You cannot assess contrast by looking at it.

---

## 11. nginx caching a container's address

**Chapter 22** · symptom, after rebuilding one service:

```
502 Bad Gateway
```

```
node-api actually at :  172.18.0.4
nginx connecting to  :  172.18.0.3
```

**Cause.** nginx resolves a `proxy_pass` hostname once at startup and caches it
forever.

**Fix.** A `resolver` directive **and** the upstream in a variable — a literal is
cached even with a resolver configured.

**Proof.** Another container was made to take the freed address so `node-api` had
to move to `172.18.0.7`; nginx followed without the web container being touched.

**Lesson.** Some bugs live only in the composition. 51 passing tests could not
have found this.

---

## 12. A manifest naming an image that does not exist

**Chapter 24** · symptom: every pod would have sat in `ImagePullBackOff`.

```
manifest : semantic-rag-search/python-service
reality  : semantic-rag-search-python-service
```

**Cause.** A slash written by hand; Compose builds with a hyphen.

**Fix.** `sed`, then verify each name against `docker image inspect`.

---

## 13. A resolver that does not exist on Kubernetes

**Chapter 24** · symptom:

```
recv() failed (111: Connection refused) while resolving,
resolver: 127.0.0.11:53
```

**Cause.** `127.0.0.11` is Docker's embedded DNS. Kubernetes runs CoreDNS at
`10.96.0.10`. Bug 11's fix had hardcoded one platform.

**Fix.** Read the nameserver from the container's own `/etc/resolv.conf` at
start-up.

---

## 14. nginx ignoring search domains

**Chapter 24** · symptom:

```
node-api could not be resolved (3: Host not found)
```

…while every other pod resolved the same name fine.

**Cause.** A normal lookup applies the search domains in `resolv.conf`. nginx's
`resolver` queries the name verbatim, so the short name is NXDOMAIN on
Kubernetes.

**Fix.** `NODE_API_UPSTREAM`, set to the fully-qualified name by the Deployment
and left at the short name under Compose.

---

## 15. Healthy, and unreachable

**Chapter 26** · symptom: every container up, every check green, site
unreachable.

**Cause.** `.env` had no `WEB_PORT`, so Compose used its 8080 default. The
firewall allowed only 80.

**Fix.** `setup.sh` appends `WEB_PORT=80` if absent.

**Lesson.** A default that is right for development is a trap in production
unless something enforces the production value.

---

## And one found while writing this book

**Chapter 18** · The rate limit was documented as per-instance, as a theoretical
caveat. Running the same eight requests against both deployments showed it is not
theoretical:

```
Compose    (1 web container)  →  200 200 200 429 429 429 429
Kubernetes (2 web replicas)   →  200 200 200 200 200 200 200 200
```

Same image, same config. On Kubernetes the limit never fires, because each nginx
keeps its own counters and the Service splits the traffic.

**Lesson.** A per-instance limit gets weaker as you scale and nothing warns you.

---

## Counting them up

| Found by | Count |
|---|---|
| Running it in a second environment | **6** (2, 11, 12, 13, 14, and the rate limit) |
| Actually calling a real service | 3 (3, 4, 5) |
| Reading the code carefully | 3 (7, 8, 9) |
| Measuring instead of looking | 1 (10) |
| Ordinary debugging | 2 (1, 6, 15) |

The largest group is *ran it somewhere else*. Not a cleverer test suite, not more
careful reading — a different environment.

That is the single most transferable thing in this book.
