// Money is stored as whole kobo and shown in naira. Times arrive as Unix epoch seconds (UTC) and are shown in WAT.
const naira = new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", minimumFractionDigits: 2 });
const count = new Intl.NumberFormat("en-NG");
const TZ = "Africa/Lagos"; // West Africa Time (UTC+1, no daylight saving)

export const formatNaira = (kobo: number) => naira.format(kobo / 100);
export const formatCount = (n: number) => count.format(n);

const watDateTime = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
export const formatWAT = (epochSeconds: number) => `${watDateTime.format(epochSeconds * 1000)} WAT`;

const watClock = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false });
export const formatClock = (d: Date) => watClock.format(d);

const watLong = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "long", day: "numeric", month: "long", year: "numeric" });
export const formatLongDate = (d: Date) => watLong.format(d);

const watHour = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "numeric", hour12: false });
export const greeting = (d: Date) => {
  const h = Number(watHour.format(d)) % 24;
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

export const weekdayShort = (isoDate: string) =>
  new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short" }).format(new Date(`${isoDate}T12:00:00+01:00`));

export const initials = (name: string) => name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase();

// 11-digit NIN shown as 1234•••••01 so the full number is not on screen.
export const maskNin = (nin: string) => (nin.length >= 6 ? `${nin.slice(0, 4)}${"•".repeat(nin.length - 6)}${nin.slice(-2)}` : nin);
export const formatGB = (bytes: number) => `${bytes / 1_000_000_000} GB`;

export const formatTimeWAT = (epochSeconds: number) => watClock.format(new Date(epochSeconds * 1000));
export const formatDuration = (seconds: number) => `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
export const formatMB = (bytes: number) => (bytes / 1_000_000).toFixed(1);
export const formatGB1 = (bytes: number) => `${(bytes / 1_000_000_000).toFixed(1)} GB`;

const watDay = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "2-digit", month: "short" });
export const formatDayWAT = (epochSeconds: number) => watDay.format(new Date(epochSeconds * 1000));

// ₦1.28M, ₦412k: for big totals in a small space.
export const formatNairaCompact = (kobo: number) => {
  const n = kobo / 100;
  return n >= 1_000_000 ? `₦${(n / 1_000_000).toFixed(2)}M` : n >= 1_000 ? `₦${Math.round(n / 1_000)}k` : naira.format(n);
};
export const formatBytesAuto = (bytes: number) =>
  bytes >= 1e12 ? `${(bytes / 1e12).toFixed(1)} TB` : bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${(bytes / 1e6).toFixed(1)} MB`;
export const formatDateShort = (isoDate: string) =>
  new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short" }).format(new Date(`${isoDate}T12:00:00+01:00`));
