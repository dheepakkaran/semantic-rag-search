/**
 * Express app assembly, kept separate from starting the server so tests can
 * import the app without opening a port.
 */

import cors from "cors";
import express, {
  type NextFunction,
  type Request,
  type Response,
} from "express";

import { routes } from "./routes.js";
import { RagServiceError } from "./ragClient.js";

export function createApp() {
  const app = express();

  app.use(cors({ origin: process.env.CORS_ORIGIN ?? "*" }));
  app.use(express.json({ limit: "5mb" }));

  app.use("/api", routes);

  app.use((_request: Request, response: Response) => {
    response.status(404).json({ error: "not found" });
  });

  // One error handler, so no route needs its own try/catch reply. A failure
  // reaching us from the retrieval service keeps its own status code; anything
  // else is our bug and becomes a 500.
  app.use(
    (error: unknown, _request: Request, response: Response, _next: NextFunction) => {
      if (error instanceof RagServiceError) {
        return response
          .status(error.status)
          .json({ error: "retrieval service failed", detail: error.message });
      }

      console.error(error);
      response.status(500).json({ error: "internal error" });
    },
  );

  return app;
}
