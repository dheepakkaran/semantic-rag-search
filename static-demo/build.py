"""Build the static demo index: the book → the app's own chunker → MiniLM
embeddings (int8) → docs/demo/index.json, plus pre-generated answers for the
sample questions with the app's own grounding prompt.

Run: static-demo/.venv/bin/python static-demo/build.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-service"))
from rag.chunker import chunk_text            # the app's chunker, unchanged
from rag.pipeline import PROMPT               # the app's grounding prompt, unchanged
from rag.embedder import MODEL_NAME           # all-MiniLM-L6-v2

OUT = ROOT / "docs/demo"
K = 4


def load_env():
    p = Path(__file__).parent / ".env"
    for line in p.read_text().splitlines() if p.exists() else []:
        k, _, v = line.partition("=")
        if k and v:
            os.environ.setdefault(k, v.strip())


def main():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME, cache_folder=str(Path(__file__).parent / ".cache"))
    chunks = []
    for f in sorted((ROOT / "book").glob("*.md")):
        if f.name == "README.md":
            continue
        text = f.read_text()
        title = text.splitlines()[0].lstrip("# ").strip()
        for i, c in enumerate(chunk_text(text)):
            chunks.append({"doc": f.stem, "title": title, "i": i, "text": c})
    t0 = time.perf_counter()
    V = model.encode([c["text"] for c in chunks], normalize_embeddings=True, batch_size=64)
    t_embed = time.perf_counter() - t0
    scale = 127 / float(np.abs(V).max())
    Q = np.round(V * scale).astype(np.int8)

    # check: int8 ranking agrees with float32 ranking on the sample questions
    qs = json.loads((Path(__file__).parent / "questions.json").read_text())
    qv = model.encode([q["q"] for q in qs], normalize_embeddings=True)
    agree, report = 0, []
    for q, v in zip(qs, qv):
        f_top = list(np.argsort(V @ v)[::-1][:K])
        q_top = list(np.argsort(Q.astype(np.float32) @ v)[::-1][:K])
        agree += f_top == q_top
        docs = [chunks[i]["doc"] for i in f_top]
        hit = (not q.get("unanswerable")) and any(e in docs for e in q["expect"])
        report.append({"q": q["q"], "top": [{"id": int(i), "doc": chunks[i]["doc"], "score": round(float(V[i] @ v), 3)} for i in f_top],
                       "expected_in_top4": hit if not q.get("unanswerable") else None, "unanswerable": bool(q.get("unanswerable"))})

    # pre-generated answers with the app's own prompt
    load_env()
    import anthropic
    client = anthropic.Anthropic()
    usage = {"in": 0, "out": 0}
    for r in report:
        ctx = "\n\n".join(f"[{n}] {chunks[h['id']]['text']}" for n, h in enumerate(r["top"], start=1))
        msg = client.messages.create(model="claude-haiku-5-5", max_tokens=1200, output_config={"effort": "low"},
                                     messages=[{"role": "user", "content": PROMPT.format(context=ctx, question=r["q"])}])
        r["answer"] = next(b.text for b in msg.content if b.type == "text").strip()
        usage["in"] += msg.usage.input_tokens; usage["out"] += msg.usage.output_tokens

    OUT.mkdir(parents=True, exist_ok=True)
    index = {"model": MODEL_NAME, "browser_model": "Xenova/all-MiniLM-L6-v2", "chunk_words": 120, "overlap_words": 20, "k": K,
             "scale": scale, "dim": int(V.shape[1]), "chunks": chunks, "vectors_int8_b64": base64.b64encode(Q.tobytes()).decode()}
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    cost = (usage["in"] * 0.10 + usage["out"] * 0.50) / 1e6
    samples = {"answer_model": "claude-haiku-5-5", "prompt": "python-service/rag/pipeline.py PROMPT", "questions": report}
    (OUT / "samples.json").write_text(json.dumps(samples, indent=1))
    stats = {"chunks": len(chunks), "chapters": len({c['doc'] for c in chunks}), "words": sum(len(c["text"].split()) for c in chunks),
             "embed_seconds_cpu": round(t_embed, 2), "index_kb": round((OUT / "index.json").stat().st_size / 1024, 1),
             "int8_top4_same_as_float32": f"{agree}/{len(qs)}",
             "sample_questions_right_chapter_in_top4": f"{sum(1 for r in report if r['expected_in_top4'])}/{sum(1 for r in report if not r['unanswerable'])}",
             "answer_cost_usd": round(cost, 4)}
    (OUT / "stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))
    for r in report:
        print(("✓" if r["expected_in_top4"] else ("–" if r["unanswerable"] else "✗")), r["q"], "→", [t["doc"][:14] for t in r["top"]], r["top"][0]["score"])
        print("   ", r["answer"][:160].replace("\n", " "))


if __name__ == "__main__":
    main()
