/**
 * MSW server for vitest (node). It starts with no handlers: the station tests register the mock
 * Station API per test (`station/mock/handlers.ts` through `station/test/utils.tsx`), and any request
 * nobody handles fails the test (`onUnhandledRequest: "error"` in setup.ts).
 */
import { setupServer } from "msw/node";

export const server = setupServer();
