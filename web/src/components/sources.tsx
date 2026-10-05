// One icon per source kind, the same everywhere a source is cited, with its reliability tier.
import {
  Archive, Building, Camera, ChartColumn, Coins, Globe, MessagesSquare, Newspaper, Satellite, SearchX, ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export const SOURCE_ICONS: Record<string, LucideIcon> = {
  audit: ShieldCheck,
  foreign_mirror: Globe,
  archive: Archive,
  statistics: ChartColumn,
  osint: Satellite,
  contributor: Camera,
  official_live: Building,
  news: Newspaper,
  social: MessagesSquare,
  absence: SearchX,
  amount: Coins,
};

export function SourceIcon({ kind, size = 14 }: { kind: string; size?: number }) {
  const Icon = SOURCE_ICONS[kind] ?? Newspaper;
  return <Icon size={size} aria-label={kind.replaceAll("_", " ")} style={{ flex: "none" }} />;
}

export function SourceLine({ kind, publisher, reliability, date }: {
  kind: string; publisher: string; reliability: string; date?: string | null;
}) {
  return (
    <span className="row small" style={{ gap: 6 }}>
      <SourceIcon kind={kind} />
      <span>{publisher}</span>
      <span className="faint">· {reliability}{date ? ` · ${date.slice(0, 10)}` : ""}</span>
    </span>
  );
}

export function formatTnd(n: number): string {
  // Thin-space thousands separators, as the sources write them.
  return `${Math.round(n).toLocaleString("en-US").replaceAll(",", " ")} TND`;
}
