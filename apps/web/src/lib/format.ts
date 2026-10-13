const dayTimeFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

export const formatDayTime = (iso: string) => dayTimeFmt.format(new Date(iso));
export const formatDateTime = (iso: string) => dateTimeFmt.format(new Date(iso));

export function formatMiles(mi: number): string {
  return mi >= 100 ? `${Math.round(mi).toLocaleString()} mi` : `${mi.toFixed(1)} mi`;
}

export function formatRate(inPerHr: number): string {
  if (inPerHr <= 0) return "0";
  return inPerHr < 0.01 ? "<0.01" : inPerHr.toFixed(2);
}

/** Value for <input type="datetime-local"> in the browser's time zone. */
export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function nextQuarterHour(from = new Date()): Date {
  const d = new Date(from);
  d.setSeconds(0, 0);
  d.setMinutes(Math.ceil((d.getMinutes() + 1) / 15) * 15);
  return d;
}

export const timeZoneName = () =>
  new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
    .formatToParts(new Date())
    .find((p) => p.type === "timeZoneName")?.value ?? "";

export function formatRanges(text: string): string {
  return text.replaceAll(/(\d)-(\d)/g, "$1\u2060\u2013\u2060$2");
}
