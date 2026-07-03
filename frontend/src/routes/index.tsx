import { createFileRoute } from "@tanstack/react-router";
import { ChatInterface } from "#/features/chat";
import { AppHeader } from "#/shared/ui";

export const Route = createFileRoute("/")({ component: Home });

function Home() {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <AppHeader />
      <main className="flex flex-1 min-h-0 flex-col px-4 sm:px-8 py-4">
        <ChatInterface />
      </main>
    </div>
  );
}
