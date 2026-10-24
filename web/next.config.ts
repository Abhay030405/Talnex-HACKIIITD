import type { NextConfig } from "next";

// The API takes a resume of up to 5 MB plus 1 MB for the rest of the form (backend/internal/http/resume.go).
// Next.js refuses form submits over 1 MB unless told otherwise.
export const FORM_BODY_LIMIT = "6mb";

const config: NextConfig = {
  // Builds one small self-contained folder for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  experimental: { serverActions: { bodySizeLimit: FORM_BODY_LIMIT } },
};

export default config;
