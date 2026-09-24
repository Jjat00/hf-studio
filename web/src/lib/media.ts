/** Duración (s) de videos subidos o enlazados, medida en el navegador: la API la necesita para
 *  cotizar modelos que cobran por segundos de video de entrada. */
const durations = new Map<string, number>();
const pending = new Map<string, Promise<number | null>>();

export function knownDuration(url: string) {
  return durations.get(url);
}

export function rememberDuration(url: string, seconds: number) {
  if (Number.isFinite(seconds) && seconds > 0) durations.set(url, seconds);
}

export function probeDuration(src: string, key = src): Promise<number | null> {
  if (durations.has(key)) return Promise.resolve(durations.get(key)!);
  if (!pending.has(key)) {
    pending.set(
      key,
      new Promise((resolve) => {
        const v = document.createElement("video");
        v.preload = "metadata";
        v.muted = true;
        const done = (value: number | null) => {
          v.removeAttribute("src");
          v.load();
          if (value !== null) rememberDuration(key, value);
          pending.delete(key);
          resolve(value);
        };
        v.onloadedmetadata = () => done(Number.isFinite(v.duration) ? v.duration : null);
        v.onerror = () => done(null);
        setTimeout(() => done(null), 15000);
        v.src = src;
      }),
    );
  }
  return pending.get(key)!;
}
