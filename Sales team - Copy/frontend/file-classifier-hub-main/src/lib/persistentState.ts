import { useState, useCallback, useEffect } from "react";

const OLD_STORAGE_PREFIX = "drive_module_state_v1:";
const STORAGE_PREFIX = "drive_module_state_v2:";
const RELOAD_COUNT_KEY = "drive_consecutive_reload_count_v2";
const MAX_RELOADS_BEFORE_CLEAR = 3; // Survives 1-2 refreshes; clears only after 3+ consecutive refreshes
const MAX_INLINE_FILE_BYTES = 4 * 1024 * 1024; // 4 MB max for inline base64 in sessionStorage

// Attach memoryStore and fileByteCache to window so Vite HMR never wipes live File objects
const globalWin = typeof window !== "undefined" ? (window as any) : {};
const memoryStore: Map<string, any> =
  globalWin.__DRIVE_MODULE_MEMORY_STORE__ || (globalWin.__DRIVE_MODULE_MEMORY_STORE__ = new Map<string, any>());
const fileBase64Cache: WeakMap<File, string> =
  globalWin.__DRIVE_FILE_BASE64_CACHE__ || (globalWin.__DRIVE_FILE_BASE64_CACHE__ = new WeakMap<File, string>());

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunkSize)));
  }
  return btoa(binary);
}

function base64ToUint8Array(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

// Run once per page load to clean up v1 keys and track consecutive browser refreshes
let reloadCheckDone = false;
function checkPageReloadLifecycle() {
  if (reloadCheckDone || typeof window === "undefined") return;
  reloadCheckDone = true;

  try {
    // Purge legacy v1 0-byte stub entries
    const v1Keys: string[] = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (k && k.startsWith(OLD_STORAGE_PREFIX)) {
        v1Keys.push(k);
      }
    }
    v1Keys.forEach((k) => sessionStorage.removeItem(k));

    const navEntries = performance.getEntriesByType?.("navigation") as PerformanceNavigationTiming[] | undefined;
    const isReload = navEntries && navEntries.length > 0 && navEntries[0].type === "reload";

    if (isReload) {
      const prevCount = parseInt(sessionStorage.getItem(RELOAD_COUNT_KEY) || "0", 10) || 0;
      const nextCount = prevCount + 1;
      if (nextCount >= MAX_RELOADS_BEFORE_CLEAR) {
        const keysToRemove: string[] = [];
        for (let i = 0; i < sessionStorage.length; i++) {
          const k = sessionStorage.key(i);
          if (k && k.startsWith(STORAGE_PREFIX)) {
            keysToRemove.push(k);
          }
        }
        keysToRemove.forEach((k) => sessionStorage.removeItem(k));
        memoryStore.clear();
        sessionStorage.setItem(RELOAD_COUNT_KEY, "0");
      } else {
        sessionStorage.setItem(RELOAD_COUNT_KEY, String(nextCount));
      }
    } else {
      sessionStorage.setItem(RELOAD_COUNT_KEY, "0");
    }
  } catch {
    // Ignore storage access errors
  }
}

function collectFilesFromValue(val: any, found: File[] = []): File[] {
  if (!val || typeof val !== "object") return found;
  if (typeof File !== "undefined" && val instanceof File) {
    if (val.size > 0 && val.size <= MAX_INLINE_FILE_BYTES && !fileBase64Cache.has(val)) {
      found.push(val);
    }
    return found;
  }
  if (Array.isArray(val)) {
    for (const item of val) collectFilesFromValue(item, found);
    return found;
  }
  for (const k of Object.keys(val)) {
    collectFilesFromValue(val[k], found);
  }
  return found;
}

function serializeWithFileStubs(value: any): string {
  return JSON.stringify(value, (_key, val) => {
    if (typeof File !== "undefined" && val instanceof File) {
      return {
        __isFileStub: true,
        name: val.name,
        size: val.size,
        type: val.type,
        lastModified: val.lastModified,
        dataBase64: fileBase64Cache.get(val) || null,
      };
    }
    return val;
  });
}

function deserializeWithFileStubs(raw: string): any {
  const parsed = JSON.parse(raw, (_key, val) => {
    if (val && typeof val === "object" && val.__isFileStub) {
      try {
        if (val.dataBase64) {
          const bytes = base64ToUint8Array(val.dataBase64);
          const f = new File([bytes], val.name || "document.pdf", {
            type: val.type || "application/pdf",
            lastModified: val.lastModified || Date.now(),
          });
          fileBase64Cache.set(f, val.dataBase64);
          return f;
        }
        // If no base64 bytes are available, mark as stub-only so queued items know they need re-selection
        const f = new File([""], val.name || "document.pdf", {
          type: val.type || "application/pdf",
          lastModified: val.lastModified || Date.now(),
        });
        (f as any).__isRestoredStubWithoutBytes = true;
        return f;
      } catch {
        return null;
      }
    }
    return val;
  });

  // Filter out any unprocessed ("queued" / "error" / "processing") queue items whose File has 0 real bytes
  if (Array.isArray(parsed)) {
    return parsed.filter((item) => {
      if (!item || typeof item !== "object") return true;
      const status = item.status || item.stage;
      const isDone = status === "complete" || status === "completed";
      if (isDone) return true;

      // Check if item.file or item.files has 0 real bytes after reload
      if (item.file && ((item.file as any).__isRestoredStubWithoutBytes || item.file.size === 0)) {
        return false;
      }
      if (
        Array.isArray(item.files) &&
        item.files.some((f: any) => !f || f.__isRestoredStubWithoutBytes || f.size === 0)
      ) {
        return false;
      }
      return true;
    });
  }

  return parsed;
}

export function readPersistedState<T>(key: string, defaultValue: T | (() => T)): T {
  checkPageReloadLifecycle();

  if (memoryStore.has(key)) {
    return memoryStore.get(key) as T;
  }

  if (typeof window !== "undefined") {
    try {
      const raw = sessionStorage.getItem(STORAGE_PREFIX + key);
      if (raw !== null) {
        const parsed = deserializeWithFileStubs(raw) as T;
        memoryStore.set(key, parsed);
        return parsed;
      }
    } catch {
      // Fallback to default
    }
  }

  const resolved = typeof defaultValue === "function" ? (defaultValue as () => T)() : defaultValue;
  memoryStore.set(key, resolved);
  return resolved;
}

export function writePersistedState<T>(key: string, value: T): void {
  memoryStore.set(key, value);
  if (typeof window !== "undefined") {
    try {
      sessionStorage.setItem(RELOAD_COUNT_KEY, "0");
      sessionStorage.setItem(STORAGE_PREFIX + key, serializeWithFileStubs(value));

      // Asynchronously cache real binary bytes for any new File objects so full File survives browser refresh
      const uncachedFiles = collectFilesFromValue(value);
      if (uncachedFiles.length > 0) {
        Promise.all(
          uncachedFiles.map(async (f) => {
            try {
              const buf = await f.arrayBuffer();
              if (buf.byteLength > 0) {
                fileBase64Cache.set(f, arrayBufferToBase64(buf));
              }
            } catch {
              // Ignore file read errors
            }
          })
        ).then(() => {
          try {
            const latest = memoryStore.get(key);
            if (latest !== undefined) {
              sessionStorage.setItem(STORAGE_PREFIX + key, serializeWithFileStubs(latest));
            }
          } catch {
            // Ignore quota errors
          }
        });
      }
    } catch {
      // Ignore quota or serialization errors; memoryStore still holds the live value
    }
  }
}

/**
 * Drop-in replacement for `useState` that:
 * 1. Keeps state alive in memory (including real File objects) when switching between sidebar modules or HMR reloads.
 * 2. Persists state + real File bytes in `sessionStorage` so a single page refresh does NOT lose files or results,
 *    only clearing after multiple (3+) consecutive refreshes.
 */
export function usePersistentState<T>(
  key: string,
  initialValue: T | (() => T)
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState<T>(() => readPersistedState(key, initialValue));

  useEffect(() => {
    setState(readPersistedState(key, initialValue));
  }, [key]);

  const setPersistentState: React.Dispatch<React.SetStateAction<T>> = useCallback(
    (updater) => {
      setState((prev) => {
        const current = memoryStore.has(key) ? (memoryStore.get(key) as T) : prev;
        const next = typeof updater === "function" ? (updater as (p: T) => T)(current) : updater;
        writePersistedState(key, next);
        return next;
      });
    },
    [key]
  );

  return [state, setPersistentState];
}
