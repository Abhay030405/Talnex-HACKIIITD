// Tailwind runs only for the docs section's vendor CSS (app/docs/docs.css); the website's own CSS is plain.
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
