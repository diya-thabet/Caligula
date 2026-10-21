import {
  Activity as ActivityIcon, BookOpen, CalendarClock, Eye, FileText, Layers, ListChecks, Route, Scale, ScrollText, Signature,
  TextSearch, type LucideIcon,
} from "lucide-react";
import type { ComponentType } from "react";
import type { CaseOverview } from "../api/types";
import { Activity } from "./Activity";
import { Audit } from "./Audit";
import { CaseFile } from "./CaseFile";
import { Claims } from "./Claims";
import { Documents } from "./Documents";
import { Evidence } from "./Evidence";
import { Hypotheses } from "./Hypotheses";
import { Overview } from "./Overview";
import { Plan } from "./Plan";
import { Summary } from "./Summary";
import { Suspicions } from "./Suspicions";
import { Timeline } from "./Timeline";

export interface Section {
  path: string;
  label: string;
  Icon: LucideIcon;
  Component: ComponentType;
  count?: (c: CaseOverview) => number | undefined;
}

// The case's left rail, in the order of docs/ui.md §3.
export const SECTIONS: Section[] = [
  { path: "", label: "Overview", Icon: BookOpen, Component: Overview },
  { path: "plan", label: "Plan", Icon: Route, Component: Plan },
  { path: "activity", label: "Activity", Icon: ActivityIcon, Component: Activity, count: (c) => c.counts?.tool_calls },
  { path: "claims", label: "Claims", Icon: ListChecks, Component: Claims },
  { path: "hypotheses", label: "Hypotheses", Icon: Layers, Component: Hypotheses },
  { path: "evidence", label: "Evidence", Icon: Scale, Component: Evidence, count: (c) => c.counts?.evidence },
  { path: "documents", label: "Documents", Icon: FileText, Component: Documents, count: (c) => c.counts?.documents },
  { path: "timeline", label: "Timeline", Icon: CalendarClock, Component: Timeline },
  { path: "suspicions", label: "Suspicions", Icon: Eye, Component: Suspicions, count: (c) => c.counts?.open_suspicions },
  { path: "summary", label: "Summary", Icon: TextSearch, Component: Summary },
  { path: "casefile", label: "Case file", Icon: Signature, Component: CaseFile },
  { path: "audit", label: "Audit log", Icon: ScrollText, Component: Audit },
];
