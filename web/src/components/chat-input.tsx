"use client";

import { ArrowUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "cn";

type ChatInputProps = {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  loading: boolean;
  className?: string;
};

export function ChatInput({ value, onChange, onSend, onKeyDown, loading, className }: ChatInputProps) {
  return (
    <div
      className={cn(
        "w-full rounded-3xl border border-border bg-card px-4 pt-4 pb-3 shadow-sm",
        className
      )}
    >
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask about CP, prerequisites, thesis rules…"
        disabled={loading}
        autoFocus
        className="max-h-48 min-h-11 resize-none border-none bg-transparent px-3 py-2 text-base shadow-none outline-none focus-visible:ring-0 md:text-base"
      />
      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Not official advice — verify with the examination office or responsible chair.
        </p>
        <Button
          onClick={onSend}
          disabled={loading || !value.trim()}
          size="icon"
          className="shrink-0 rounded-full"
          aria-label="Send"
        >
          <ArrowUp className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
