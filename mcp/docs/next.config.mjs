import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** A static site (out/): no server needed, so it can be hosted anywhere. Not part of docker-compose. */
/** @type {import('next').NextConfig} */
const config = {
  output: 'export',
  reactStrictMode: true,
  // mcp/ has its own lockfile; this site is its own project
  turbopack: { root: import.meta.dirname },
};

export default withMDX(config);
