# Static demo (GitHub Pages)

`docs/` is a live, server-free version of the retrieval half of this app: the project's own book, chunked by `python-service/rag/chunker.py` and embedded with the same all-MiniLM-L6-v2 model, searched in the browser with transformers.js.

```
uv venv static-demo/.venv && uv pip install --python static-demo/.venv/bin/python -r static-demo/requirements.txt
echo "ANTHROPIC_API_KEY=..." > static-demo/.env      # only for the pre-generated sample answers
static-demo/.venv/bin/python static-demo/build.py     # → docs/demo/index.json, samples.json, stats.json
```

- `questions.json`: the sample questions, with the chapter expected for each written before the build ran.
- Sample answers use the app's own prompt (`rag/pipeline.py` `PROMPT`) on the top 4 passages, generated once with Claude Haiku 5.5 (cost in `stats.json`).
- Vectors are stored as int8; the browser runs the 8-bit model, so its ranking is close to, not identical with, the full app's. Sample answers always show the passages they were written from.
