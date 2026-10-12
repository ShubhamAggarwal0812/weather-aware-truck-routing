export function Spinner({ className = "h-4 w-4", tone = "dark" }: { className?: string; tone?: "dark" | "light" }) {
  const colors = tone === "light" ? "border-white/30 border-t-white" : "border-slate-300 border-t-slate-700";
  return (
    <span aria-hidden className={`inline-block shrink-0 animate-spin rounded-full border-2 ${colors} ${className}`} />
  );
}
