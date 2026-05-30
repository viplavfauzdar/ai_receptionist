import type { Config } from "jest";

const config: Config = {
  testEnvironment: "node", // middleware runs in the edge runtime (node-like), not jsdom
  transform: {
    "^.+\\.tsx?$": ["@swc/jest", {}],
  },
  testMatch: ["**/__tests__/**/*.test.ts?(x)"],
  moduleNameMapper: {
    // Stub Next.js internals not needed for middleware unit tests
    "^next/server$": "<rootDir>/__tests__/__mocks__/next-server.ts",
  },
};

export default config;
