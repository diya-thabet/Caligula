import { BookOpen, FileText, ListChecks, Scale, type LucideIcon } from "lucide-react";
import type { ComponentType } from "react";
import type { CaseOverview } from "../api/types";
import { Claims } from "./Claims";
import { Documents } from "./Documents";
import { Evidence } from "./Evidence";
import { Overview } from "./Overview";

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
  { path: "claims", label: "Claims", Icon: ListChecks, Component: Claims },
  { path: "evidence", label: "Evidence", Icon: Scale, Component: Evidence, count: (c) => c.counts?.evidence },
  { path: "documents", label: "Documents", Icon: FileText, Component: Documents, count: (c) => c.counts?.documents },
];
