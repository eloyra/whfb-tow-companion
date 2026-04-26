import { createFileRoute } from "@tanstack/react-router";
import { ThemeToggle } from "#/shared/ui/ThemeToggle.tsx";

export const Route = createFileRoute("/")({ component: Home });

function Home() {
  return (
    <div className="p-8">
      <ThemeToggle />
      <h1 className="text-4xl font-bold">Welcome to TanStack Start</h1>
      <p className="mt-4 text-lg">
        Edit <code>src/routes/index.tsx</code> to get started.
      </p>
    </div>
  );
}
