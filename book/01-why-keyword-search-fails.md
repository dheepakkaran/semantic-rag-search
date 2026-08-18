# Chapter 1 — Why keyword search fails

## The moment this project started

I was taking 7000-level courses. Each one came with reading — lecture notes,
papers, slide decks. By the middle of the term I had a few hundred pages of it
sitting in a folder.

One evening I wanted to find something I half-remembered. Something about how
you stop a network from just memorising its training data. I opened the notes,
pressed `Ctrl+F`, and typed:

```
memorising
```

Two results. Neither was the one I wanted.

I tried again:

```
overfitting
```

Better. But I only knew to search for *overfitting* because I already half-knew
the answer. If I had known the word, I would not have needed to search.

That is the whole problem in one sentence:

> **`Ctrl+F` finds the words you already know. It cannot find the words you are
> looking for.**

## Why this happens

`Ctrl+F` matches characters. It has no idea that these two sentences are about
the same thing:

```
how do I stop my network memorising?

Dropout randomly switches off units during training, so the network
cannot rely on one particular path and has to spread the work.
```

Read them yourself and the connection is obvious. To a character-matching
search they share almost nothing — `the`, `network`, `to`. The words that carry
the meaning (*memorising* / *dropout*, *stop* / *cannot rely on*) do not overlap
at all.

This is not a flaw in `Ctrl+F`. It is doing exactly what it was built to do. The
mismatch is that **you think in meanings and it searches in characters.**

## The gap has a name

In information retrieval this is called the **vocabulary mismatch problem**, and
it is old. The person asking a question and the person who wrote the answer
rarely choose the same words. A student writes *"stop memorising"*. A textbook
writes *"regularisation"*. A paper writes *"reducing generalisation error"*.

All three mean the same thing. No amount of clever character matching connects
them, because the connection is not in the characters.

## What would actually help

Imagine a search that worked like a friend who had read your notes. You would
not have to guess their vocabulary. You would say what you meant, and they would
say "oh, you want the bit about dropout."

To build that, we need a way for a computer to answer one question:

> **How close in meaning are these two pieces of text?**

Not *how many words do they share*. How close in **meaning**.

If we can answer that, everything else follows. Take the question, compare it
against every paragraph of the notes by meaning, and return the closest ones.

## The trick: turn meaning into position

Here is the idea that makes it work, and it is worth sitting with for a minute
because everything else in this book rests on it.

**Represent each piece of text as a point in space.** Choose the positions so
that texts with similar meanings end up near each other.

That sounds like magic, but consider a two-dimensional version you could draw on
paper. Put "cat" and "kitten" close together. Put "dog" nearby, because it is
also a pet. Put "gradient descent" far away in another corner, with "learning
rate" beside it.

```
                    gradient descent
                       •
                          • learning rate
                                              • kitten
                                            •
                                          cat
                                              • dog
```

Now "how do I train a network?" lands somewhere near the top-left cluster, and
finding the closest points gives you the training notes, not the pet ones.

Real systems use a few hundred dimensions rather than two — the one in this book
uses 384 — but the idea does not change. **Nearness in space stands in for
closeness in meaning.**

Those points are called **embeddings**, and a model produces them. Chapter 5
covers how.

## What this buys us

Once text is points in space, the search becomes arithmetic:

1. Turn every paragraph of the notes into a point. Do this once.
2. Turn the question into a point.
3. Find the paragraphs whose points are nearest the question's point.

Step 3 is a distance calculation. Computers are extremely good at those.

And critically, nothing here cares about the actual words. *"stop memorising"*
and *"dropout"* land near each other because the model that placed them has read
enough text to know they belong to the same topic. The vocabulary mismatch
simply stops being a problem.

## Where the answer comes from

Finding the right paragraph is most of the battle. But there is one more step
worth having.

Once you have the three paragraphs that matter, you could just read them. Often
that is enough. But sometimes the answer is spread across all three, and you
would rather have it in a sentence.

So we add a second stage: hand those paragraphs to a language model and ask it
to answer **using only them**.

That last part is not a detail. A language model already knows what dropout is —
it will happily answer without your notes at all. What we want is an answer
*from the notes*, so we can check it. So the instruction is explicit, and the
answer comes back with the paragraphs it used, numbered, shown underneath.

That combination — retrieve, then generate from what you retrieved — is what
**RAG** means. Chapter 3 pulls the two halves apart properly.

## What we are going to build

By the end of this book:

- Paste your notes into a web page.
- Ask a question in your own words.
- Get an answer built only from your notes, with the source paragraphs shown
  beneath it so you can verify every claim.
- Ask something your notes do not cover and be told **"I do not know"** rather
  than being handed a confident invention.

That last behaviour is the one worth showing people. It is also the one most
demos quietly skip.

## What we are *not* going to build

Worth saying now, because it shapes every chapter that follows.

We will not use a vector database. We will not use LangChain or LlamaIndex. We
will not fine-tune anything. We will not need a GPU.

Not because those are bad — because for this problem, at this size, they cost
more than they give. Chapter 19 measures exactly how much, and the number is
smaller than you would guess.

Every one of those omissions is a decision with a reason, and the reasons are in
this book. That is worth more than the code.

---

## What you should take from this chapter

| | |
|---|---|
| The problem | You search in words; you think in meanings |
| Why it happens | Question and source rarely share vocabulary |
| The idea | Put text in space so nearness means similarity |
| The two stages | Find the right passages, then answer from them |
| The rule | The answer must be checkable against its sources |

---

**Next:** [Chapter 2 — Setting up](02-setting-up.md), where we build the
environment and walk into the first two traps.
