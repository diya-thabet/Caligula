// Who acts. Until sign-in exists (roadmap F0b) the interface asks for a name once and keeps it in
// this browser; it goes to the ledger with every decision. Where storage is unavailable (private
// windows, blocked site data) the name lasts until the page is closed.
const KEY = "caligula.user";
let memory: string | null = null;

export function currentUser(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return memory;
  }
}

export function setUser(name: string): void {
  try {
    window.localStorage.setItem(KEY, name.trim());
  } catch {
    memory = name.trim();
  }
}
