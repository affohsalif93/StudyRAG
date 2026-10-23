export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 text-base text-muted-foreground">
      <span>Thinking</span>
      <span className="flex items-end gap-0.5">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground" />
      </span>
    </div>
  );
}
