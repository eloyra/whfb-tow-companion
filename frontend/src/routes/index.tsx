import { createFileRoute } from "@tanstack/react-router";
import { ChatInterface } from "#/features/chat";
import { ThemeToggle } from "#/shared/ui/ThemeToggle.tsx";

export const Route = createFileRoute("/")({ component: Home });

function Home() {
  return (
    <div className="p-8">
      <ThemeToggle />
      <ChatInterface />
    </div>
  );
}
