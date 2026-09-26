import { Activity as ActivityIcon, BookOpen, FileText, ListChecks, Route, Scale, type LucideIcon } from "lucide-react";
import type { ComponentType } from "react";
import type { CaseOverview } from "../api/types";
import { Activity } from "./Activity";
import { Claims } from "./Claims";
import { Documents } from "./Documents";
import { Evidence } from "./Evidence";
import { Overview } from "./Overview";
import { Plan } from "./Plan";

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
  { path: "evidence", label: "Evidence", Icon: Scale, Component: Evidence, count: (c) => c.counts?.evidence },
  { path: "documents", label: "Documents", Icon: FileText, Component: Documents, count: (c) => c.counts?.documents },
];
