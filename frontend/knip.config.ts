import type { KnipConfig } from "knip";

const config: KnipConfig = {
  entry: [
    "src/routes/**/*.tsx",
    "src/router.tsx",
  ],
  project: ["src/**/*.{ts,tsx}", "tests/**/*.ts"],
  ignoreDependencies: [
    "@tailwindcss/typography",
    "tw-animate-css",
    "@heroui/styles",
    "@tanstack/router-plugin",
    "lucide-react",
  ],
  ignoreBinaries: ["react-compiler-healthcheck"],
};

export default config;
