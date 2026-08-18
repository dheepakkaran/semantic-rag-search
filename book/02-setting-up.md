# Chapter 2 — Setting up

This chapter gets you to a folder where the first line of real code can run. It
is short, but it contains two traps that cost real time on this project, so it
is worth reading rather than skimming.

## What you need

| | Why |
|---|---|
| **Python 3.10 or newer** | The code uses `X \| None` type syntax, which arrived in 3.10 |
| **About 3 GB of disk** | Most of it is PyTorch, which arrives as a dependency |
| **A text editor** | Anything |

You do **not** need a GPU, Docker, or a cloud account yet. Those come in Parts
VII and IX.

Check what you have:

```bash
python3 --version
```

```
Python 3.10.1
```

Anything from `3.10` up is fine.

## The folder

```bash
mkdir semantic-rag-search && cd semantic-rag-search
```

Everything lives under here.

## The virtual environment

Python installs packages globally by default. That is a problem the moment you
have two projects that want different versions of the same library — and this
project wants a very specific stack.

A **virtual environment** is a private folder of packages belonging to one
project.

```bash
python3 -m venv venv
```

That creates a `venv/` directory. To use it, either activate it:

```bash
source venv/bin/activate
```

…or call its Python directly:

```bash
./venv/bin/python --version
```

This book uses the second form throughout. It is more typing, but it is
unambiguous — you always know which Python is running, and you cannot forget to
activate.

> **Trap 1: a virtual environment cannot be moved**
>
> Partway through this project the folder was reorganised and `venv/` moved with
> it. Then:
>
> ```
> ./venv/bin/pip: bad interpreter:
>   /old/path/venv/bin/python3: no such file or directory
> ```
>
> A virtualenv hardcodes its own absolute path into the scripts inside `bin/`.
> Move the folder and every wrapper script points at a path that no longer
> exists.
>
> Two fixes. The quick one: call `./venv/bin/python -m pip` instead of
> `./venv/bin/pip` — the `python` binary itself is a symlink and survives the
> move. The proper one: delete `venv/` and recreate it.
>
> The lesson: `venv/` is disposable. Never commit it, never move it, and never
> be sad about deleting it.

## The first packages

```bash
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install "sentence-transformers>=3.0" numpy python-dotenv
```

This takes a few minutes and downloads more than you expect. Here is what
actually arrives:

| Package | Size | What it is |
|---|---|---|
| `torch` | **511 MB** | The tensor library that runs the model |
| `scipy` | 92 MB | Scientific computing, pulled in as a dependency |
| `transformers` | 89 MB | Hugging Face model loading |
| `sympy` | 55 MB | Symbolic maths, a torch dependency |
| `scikit-learn` | 42 MB | More scientific computing |
| `numpy` | 29 MB | Arrays. We use this directly |
| **Total venv** | **978 MB** | |

Nearly a gigabyte, and 511 MB of it is PyTorch. Hold on to that number — in
Chapter 20 it becomes the single biggest problem in deploying this thing, and in
Chapter 27 it decides which cloud plan you need.

Check it worked:

```bash
./venv/bin/python -c "import sentence_transformers, numpy; print('ok')"
```

```
ok
```

## Keeping secrets out of the code

Later we will call a hosted model, and that needs an API key. Keys do not belong
in source code — not because someone might read your laptop, but because the
moment you push to GitHub the key is public and permanent. Git history does not
forget.

The convention is a file called `.env`:

```bash
cat > .env.example <<'EOF'
# Copy to .env and fill in. .env is gitignored — never commit real keys.
LLM_PROVIDER=mock
GEMINI_API_KEY=
EOF

cp .env.example .env
```

Two files, and the difference matters:

| File | Committed? | Contains |
|---|---|---|
| `.env.example` | **Yes** | The *names* of the settings, no values |
| `.env` | **No** | Your real keys |

The example file is documentation: it tells the next person (including you in
six months) which settings exist.

## Making sure `.env` cannot be committed

```bash
cat > .gitignore <<'EOF'
.env
venv/
__pycache__/
*.pyc
.DS_Store
EOF
```

Then verify, rather than trusting:

```bash
git init
git check-ignore -v .env
```

```
.gitignore:1:.env	.env
```

That output means: *rule on line 1 of `.gitignore` matches `.env`*. Silence
would mean it is **not** ignored.

> **Do this check every time.** Later in this project a whole PostgreSQL data
> directory nearly got committed because nobody had added it to `.gitignore`.
> It was caught by running exactly this command before the first push.

## What the folder looks like now

```
semantic-rag-search/
├── venv/              ← 978 MB, gitignored, disposable
├── .env               ← your keys, gitignored
├── .env.example       ← committed, no values
└── .gitignore
```

## A note on which Python is running

You will hit this eventually, so here it is early.

There is a difference between these two commands:

```bash
./venv/bin/pytest          # runs pytest's launcher script
./venv/bin/python -m pytest # runs pytest as a module of this Python
```

They usually behave identically. Usually.

> **Trap 2: `python -m` changes the import path**
>
> When you run `python -m something`, Python adds the **current directory** to
> the import path. When you run a launcher script directly, it does not.
>
> This project's tests passed locally with `./venv/bin/python -m pytest` and
> would have failed in CI, which runs a bare `pytest`, with:
>
> ```
> ModuleNotFoundError: No module named 'rag'
> ```
>
> The fix was one line in `pytest.ini`:
>
> ```ini
> [pytest]
> pythonpath = .
> ```
>
> Now the path is set explicitly and both forms work. Chapter 7 covers this
> where it belongs, but the general lesson lands here: **when something works
> one way and not another, the difference is usually an implicit path.**

## What is next

The environment is ready. Before writing retrieval code, Chapter 3 pins down
what RAG actually is — because the term gets used for two quite different things
and mixing them up will cost you in an interview.

---

## Checklist

- [ ] `python3 --version` shows 3.10 or newer
- [ ] `venv/` created, and you know to call `./venv/bin/python`
- [ ] `sentence-transformers`, `numpy`, `python-dotenv` installed
- [ ] `.env` and `.env.example` exist
- [ ] `git check-ignore -v .env` prints a match

---

**Next:** [Chapter 3 — What RAG actually is](03-what-rag-actually-is.md)
