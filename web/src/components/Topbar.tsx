import { Moon, Scale, Sun, UserRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useUser } from "../hooks";

const THEME_KEY = "caligula.theme";

function readTheme(): string {
  try {
    return window.localStorage.getItem(THEME_KEY) ?? "system";
  } catch {
    return "system";
  }
}

function applyTheme(theme: string) {
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* the choice lasts this visit */
  }
}

export function Topbar() {
  const [user, setUser] = useUser();
  const [editing, setEditing] = useState(!user);
  const [draft, setDraft] = useState(user ?? "");
  const [theme, setTheme] = useState(() => {
    const t = readTheme();
    applyTheme(t);
    return t;
  });
  const nextTheme = theme === "system" ? "dark" : theme === "dark" ? "light" : "system";

  return (
    <header className="topbar">
      <Link to="/" className="row brand" style={{ color: "var(--text)" }}>
        <Scale size={16} /> Caligula
      </Link>
      <span className="faint">investigation workspace</span>
      <span className="spacer" />
      {editing ? (
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            if (draft.trim()) {
              setUser(draft);
              setEditing(false);
            }
          }}
        >
          <label className="small muted" htmlFor="acting-as">Acting as</label>
          <input id="acting-as" className="input" style={{ width: 200 }} value={draft}
                 placeholder="Your name and role" onChange={(e) => setDraft(e.target.value)} />
          <button className="btn" type="submit">Save</button>
        </form>
      ) : (
        <button className="btn ghost" onClick={() => setEditing(true)} title="Recorded in the ledger with every decision">
          <UserRound size={14} /> {user}
        </button>
      )}
      <button className="btn ghost" aria-label={`Theme: ${theme}`} title={`Theme: ${theme}`}
              onClick={() => { applyTheme(nextTheme); setTheme(nextTheme); }}>
        {theme === "dark" ? <Moon size={14} /> : <Sun size={14} />} {theme}
      </button>
    </header>
  );
}
