"use client";

import { useEffect, useRef, useState } from "react";

import Link from "next/link";

import { ChatInput } from "@/components/chat-input";
import { MessageBubble, type ChatMessage } from "@/components/message-bubble";
import { askQuestion, type ChatTurn } from "@/lib/api";

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async () => {
    const question = input.trim();
    if (!question || loading) return;

    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", content: question };
    const history: ChatTurn[] = messages.map((m) => ({
      role: m.role === "error" ? "assistant" : m.role,
      content: m.content,
    }));

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const result = await askQuestion(question, history);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: result.answer,
          sources: result.sources,
          question,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "error",
          content: err instanceof Error ? err.message : "Something went wrong reaching StudyRAG.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const hasMessages = messages.length > 0;

  if (!hasMessages) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background px-4">
        <div className="w-full max-w-2xl space-y-6">
          <div className="text-center">
            <h1 className="text-3xl font-semibold text-foreground">
              StudyRAG <span className="text-muted-foreground">· RWTH Aachen</span>
            </h1>
            <p className="mt-2 text-base text-muted-foreground">
              Citation-backed Q&amp;A over the Master Informatik study regulations, plus a
              career-goal-driven elective recommender — both backed by the same regulations.
            </p>
          </div>
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={handleSend}
            onKeyDown={handleKeyDown}
            loading={loading}
          />
          <div className="flex justify-center gap-4 text-sm text-muted-foreground">
            <Link href="/quiz" className="underline hover:text-foreground">
              Find electives for my goal
            </Link>
            <Link href="/graph" className="underline hover:text-foreground">
              Explore the prerequisite graph
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-sm font-medium text-foreground">
          StudyRAG <span className="text-muted-foreground">· RWTH Aachen</span>
        </h1>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl space-y-6 px-4 py-6">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {loading && <p className="text-base text-muted-foreground">Thinking…</p>}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="px-4 pt-2 pb-4">
        <div className="mx-auto max-w-2xl">
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={handleSend}
            onKeyDown={handleKeyDown}
            loading={loading}
          />
        </div>
      </div>
    </div>
  );
}
