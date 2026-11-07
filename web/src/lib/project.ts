import { useSyncExternalStore } from "react";

/** Proyecto activo: lo que se genere en los estudios y los chats nuevos van a él. Vive en el navegador. */
const KEY = "hfs.project";
const EVENT = "hfs-project";

export type ActiveProject = { id: string; name: string };

function read(): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Id del proyecto activo (null si no hay). */
export function activeProject(): string | null {
  const raw = read();
  if (!raw) return null;
  try {
    return (JSON.parse(raw) as ActiveProject).id ?? null;
  } catch {
    return null;
  }
}

export function setActiveProject(p: ActiveProject | null) {
  try {
    if (p) window.localStorage.setItem(KEY, JSON.stringify(p));
    else window.localStorage.removeItem(KEY);
  } catch {
    /* sin almacenamiento: queda sin proyecto */
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

/** El proyecto activo, al día en todas las pestañas. */
export function useActiveProject(): ActiveProject | null {
  const raw = useSyncExternalStore(subscribe, read, () => null);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ActiveProject;
  } catch {
    return null;
  }
}
