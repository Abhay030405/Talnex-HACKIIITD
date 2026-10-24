import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** Runs as a small Next.js server: the API playground's proxy and the test-token helper are server routes.
 * Not part of docker-compose. */
/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // mcp/ has its own lockfile; this site is its own project
  turbopack: { root: import.meta.dirname },
};

export default withMDX(config);
