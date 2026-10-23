"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { ThumbsUp, ThumbsDown, ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { sendFeedback, sourceLabel, type Source } from "@/lib/api";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "error";
  content: string;
  sources?: Source[];
  /** For assistant messages: the user question this answer responds to. */
  question?: string;
};

export function MessageBubble({ message }: { message: ChatMessage }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-secondary px-4 py-2 text-secondary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "error") {
    return (
      <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2 text-base text-destructive">
        {message.content}
      </div>
    );
  }

  const handleRate = async (next: "up" | "down") => {
    setRating(next);
    if (next === "down") {
      setShowComment(true);
      return; // wait for an optional comment before sending
    }
    await submitFeedback(next, "");
  };

  const submitFeedback = async (finalRating: "up" | "down", finalComment: string) => {
    try {
      await sendFeedback({
        question: message.question ?? "",
        answer: message.content,
        sources: message.sources ?? [],
        rating: finalRating,
        comment: finalComment || undefined,
      });
    } finally {
      setSubmitted(true);
      setShowComment(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="prose max-w-none dark:prose-invert">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>

      {message.sources && message.sources.length > 0 && (
        <div>
          <button
            onClick={() => setSourcesOpen((v) => !v)}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            {sourcesOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {message.sources.length} source{message.sources.length > 1 ? "s" : ""}
          </button>
          {sourcesOpen && (
            <ol className="mt-1 space-y-1 text-sm text-muted-foreground">
              {message.sources.map((s, i) => (
                <li key={i}>
                  [{i + 1}] {sourceLabel(s)}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      <div className="flex items-center gap-1">
        {submitted ? (
          <span className="text-sm text-muted-foreground">Thanks for the feedback.</span>
        ) : (
          <>
            <Button
              variant={rating === "up" ? "secondary" : "ghost"}
              size="icon"
              className="h-7 w-7"
              onClick={() => handleRate("up")}
              aria-label="Good answer"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant={rating === "down" ? "secondary" : "ghost"}
              size="icon"
              className="h-7 w-7"
              onClick={() => handleRate("down")}
              aria-label="Bad answer"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
      </div>

      {showComment && !submitted && (
        <div className="flex gap-2">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What was wrong? (optional)"
            className="h-16 text-base md:text-base"
          />
          <Button size="sm" onClick={() => submitFeedback("down", comment)}>
            Send
          </Button>
        </div>
      )}
    </div>
  );
}
