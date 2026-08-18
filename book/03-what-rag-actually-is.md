# Chapter 3 — What RAG actually is

## Three letters, two halves

**RAG** stands for **Retrieval-Augmented Generation**. The name is unusually
honest — it tells you exactly what happens, in order:

```
Retrieval          find the relevant text
     ↓
Augmented          add that text to the prompt
     ↓
Generation         let a model write the answer from it
```

Most confusion about RAG comes from people building only the first half and
calling it RAG, or building only the second and calling it RAG. They are
different things and they fail in different ways.

## The first half: retrieval

You have a pile of documents and a question. Retrieval finds the passages most
likely to contain the answer.

```
question  ──►  [ retrieval ]  ──►  passage 1  (score 0.57)
                    ▲               passage 2  (score 0.28)
                    │               passage 3  (score 0.21)
              your documents
```

No model writes anything here. The output is text you already had, sorted by
relevance.

**This is useful on its own.** A ranked list of the three most relevant
paragraphs from your notes is a good result. The system in this book exposes it
as its own endpoint, `/search`, because sometimes that is all you want — and
because it costs nothing to run.

Chapters 4 to 7 build this half.

## The second half: generation

Now you take those passages, put them in a prompt, and ask a model to answer
using them.

```
passage 1 ┐
passage 2 ├─►  [ prompt ]  ──►  language model  ──►  "Dropout switches off
passage 3 ┘                                           units at random [1]…"
question  ┘
```

The model is not searching. It has been handed the relevant text and asked to
turn it into an answer.

Chapters 8 and 9 build this half.

## Why the distinction matters

Say the system gives you a wrong answer. What went wrong?

There are exactly two possibilities, and they need opposite fixes:

| | What happened | What to fix |
|---|---|---|
| **Retrieval failed** | The right passage was never found. The model answered from the wrong text and had no chance | Chunking, the embedding model, how many passages you pass |
| **Generation failed** | The right passage *was* there, and the model still got it wrong | The prompt, the model |

If you cannot tell these apart, you will spend a week tuning prompts when the
real problem is that your chunks are the wrong size.

This is why the system in this book keeps the two halves separately testable,
and why the interface always shows the passages under the answer. When something
looks wrong you glance at the sources and know immediately which half to blame.

> This is also the single best answer to give when an interviewer asks how you
> would debug a RAG system. Most people say "tune the prompt." The better answer
> is "first find out whether retrieval handed the model the right passage at
> all."

## The mistake people make with the name

Two symmetrical errors, both common.

**Calling retrieval-only "RAG."** You build semantic search — chunking,
embeddings, similarity — and describe it as a RAG system. There is no
generation. Anyone who works on this will notice in one question: *"what model
generates the answer?"*

**Calling generation-only "RAG."** You paste a document into a chat window and
ask about it. That is a long prompt, not RAG — there is no retrieval step
choosing what goes in.

Neither is a crime. Both are fine systems. But name them accurately:

| What you built | What to call it |
|---|---|
| Chunk, embed, rank, return passages | **Semantic search** / vector search |
| Paste a document into a prompt | **Long-context prompting** |
| Retrieve *then* generate from what you retrieved | **RAG** |

## Why not just ask the model directly?

Fair question. Modern models know a lot. Why bother with any of this?

Three reasons, and only the third is the real one.

**1. The model does not know your notes.** Your lecture notes, your meeting
minutes, your company's documentation — none of it was in the training data.

**2. Context windows are finite and expensive.** Even where you could paste
everything, you would pay for every token on every question.

**3. You cannot check the answer.** This is the one that matters.

Ask a model directly and you get fluent prose with no way to verify it. Ask a
RAG system and you get an answer **plus the passages it came from**. You can
read the passage and see whether the answer is supported.

That property has a name: **grounding**. It is the whole point.

## Grounding, concretely

Here is the prompt this project uses. It is not long, and every line is doing
work:

```
Answer the question using only the notes below.
Cite the notes you use like [1] or [2].
If the notes do not contain the answer, say you do not know.

Notes:
[1] <first retrieved passage>
[2] <second retrieved passage>

Question: <the question>
Answer:
```

| Line | Why it is there |
|---|---|
| *"using only the notes below"* | Without it, the model answers from training data and you cannot tell |
| *"Cite the notes you use"* | Turns a claim into a checkable claim |
| *"say you do not know"* | Gives the model permission to fail, which is what stops invention |

That third line is worth dwelling on. A model with no way out will produce
*something* — that is what "hallucination" usually is. Give it an acceptable
failure and it takes it.

The test for whether grounding works is simple, and this project passes it:

```
Q: who won the 2019 cricket world cup?
A: I do not know.
```

The model knows the answer. It is in the training data. But it is not in the
notes, so the system says so. Chapter 8 covers how to check this properly.

## What RAG is not

A few things that get bundled under the name and are not part of it:

| | |
|---|---|
| **Fine-tuning** | Changing the model's weights. RAG changes the *prompt*. They solve different problems |
| **A vector database** | A tool that makes retrieval fast at scale. Useful; not required. Chapter 19 measures whether we need one |
| **An agent** | Something that decides and acts in a loop. RAG is one retrieval, one generation |
| **LangChain** | A framework that packages RAG patterns. This project does not use one, for reasons in Chapter 6 |

## The whole system, in one picture

```
INGEST (once per document)
   document ──► chunk ──► embed ──► store

ASK (every question)
   question ──► embed ──► compare with every chunk ──► top k passages
                                                            │
                                              ┌─────────────┴─────────────┐
                                              │                           │
                                       /search returns              /ask puts them
                                       them directly                in a prompt ──► model
                                                                            │
                                                                     answer + citations
```

That is the entire architecture. Everything else in this book — the databases,
the containers, Kubernetes, AWS — is plumbing around this core.

The core itself is about thirty lines. Chapter 6 shows all of them.

---

## What you should take from this chapter

| | |
|---|---|
| RAG = | Retrieval **then** Generation, in that order |
| Retrieval alone = | Semantic search. Useful, but not RAG |
| Generation alone = | Long-context prompting. Also not RAG |
| Why bother = | Grounding — the answer is checkable |
| The debugging question = | Did retrieval hand the model the right passage? |

---

**Next:** [Chapter 4 — Chunking](04-chunking.md), where we split documents and
measure our way to the right size.
