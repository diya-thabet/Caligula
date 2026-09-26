// Who acts. Until sign-in exists (roadmap F0b) the interface asks for a name once and keeps it in
// this browser; it goes to the ledger with every decision. Storage can be unavailable (private
// windows, blocked site data), so a name set this session is also kept in memory.
const KEY = "caligula.user";
let memory: string | null = null;

export function currentUser(): string | null {
  try {
    return window.localStorage.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function setUser(name: string): void {
  memory = name.trim();
  try {
    window.localStorage.setItem(KEY, memory);
  } catch {
    /* kept in memory only */
  }
}
