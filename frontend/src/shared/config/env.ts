import { z } from "zod";

const envSchema = z.object({
  apiUrl: z.string().url().default("http://localhost:8000"),
});

export const env = envSchema.parse({
  apiUrl: import.meta.env.VITE_API_URL,
});
