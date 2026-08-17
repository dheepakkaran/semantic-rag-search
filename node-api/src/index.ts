/** Entry point: create the schema, then listen. */

import "dotenv/config";

import { createApp } from "./app.js";
import { initSchema } from "./db.js";

const PORT = Number(process.env.PORT ?? 3001);

async function main(): Promise<void> {
  await initSchema();

  createApp().listen(PORT, () => {
    console.log(`node-api listening on :${PORT}`);
    console.log(`retrieval service at ${process.env.RAG_SERVICE_URL ?? "http://localhost:8000"}`);
  });
}

main().catch((error) => {
  console.error("failed to start:", error);
  process.exit(1);
});
