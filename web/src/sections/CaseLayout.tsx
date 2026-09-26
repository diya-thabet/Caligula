import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import type { CaseOverview } from "../api/types";
import { Query } from "../components/Query";
import { useCase, useLiveCase } from "../hooks";
import { usePanel } from "../panel";
import { CaseHeader } from "./CaseHeader";
import { ContextPanel } from "./ContextPanel";
import { SECTIONS } from "./registry";

const POC = "Proof of concept — internal working document. Not reviewed by a lawyer or an editor. "
  + "Not for publication or circulation outside the project.";

export function useCaseContext() {
  return useOutletContext<CaseOverview>();
}

export function CaseLayout() {
  const { caseId = "" } = useParams();
  const q = useCase(caseId);
  const { selected } = usePanel();
  useLiveCase(caseId);
  return (
    <Query q={q}>
      {(c) => (
        <div style={{ display: "grid", gridTemplateRows: "auto auto 1fr", minHeight: 0 }}>
          {c.poc && <div className="banner poc" role="note">{POC}</div>}
          <CaseHeader c={c} />
          <div className="workspace">
            <nav className="rail" aria-label="Case sections">
              {SECTIONS.map((s) => (
                <NavLink key={s.path} to={s.path} end={s.path === ""}
                         className={({ isActive }) => (isActive ? "active" : "")}>
                  <s.Icon size={15} /> {s.label}
                  {s.count?.(c) ? <span className="count">{s.count(c)}</span> : null}
                </NavLink>
              ))}
            </nav>
            <main className="centre"><div className="page"><Outlet context={c} /></div></main>
            {selected && <ContextPanel caseId={c.id} selected={selected} />}
          </div>
        </div>
      )}
    </Query>
  );
}
