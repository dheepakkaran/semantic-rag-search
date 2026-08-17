/**
 * PostgreSQL holds document metadata: a title, a chunk count, a timestamp.
 *
 * This is the relational half of the storage split. Documents are a small,
 * fixed-shape set of rows that get listed, counted and joined against search
 * results — exactly what a relational table is for. The chunks and their
 * vectors live in MongoDB instead, because those are variable-length blobs
 * with no relationships worth modelling.
 */

import { Pool } from "pg";

export interface DocumentRow {
  id: number;
  title: string;
  chunk_count: number;
  created_at: string;
}

export const pool = new Pool({
  connectionString:
    process.env.DATABASE_URL ?? "postgres://rag:rag@localhost:5432/rag",
});

/**
 * Created on startup rather than through a migration tool. One table with no
 * history does not need migrations; if a second table arrives, it will.
 */
export async function initSchema(): Promise<void> {
  await pool.query(`
    create table if not exists documents (
      id          serial primary key,
      title       text        not null,
      chunk_count integer     not null default 0,
      created_at  timestamptz not null default now()
    )
  `);
}
