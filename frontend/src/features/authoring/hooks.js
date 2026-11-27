import { useCallback, useEffect, useRef, useState } from "react";

/** Load a resource and expose loading, error, reload and local replacement. */
export function useResource(load, deps) {
  const [state, setState] = useState({ data: undefined, error: null, loading: true });
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    setState(s => ({ ...s, loading: true, error: null }));
    return load().then(
      data => { if (ticket === latest.current) setState({ data, error: null, loading: false }); return data; },
      error => { if (ticket === latest.current) setState(s => ({ ...s, error, loading: false })); },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  const replace = useCallback(data => setState({ data, error: null, loading: false }), []);
  return { ...state, reload, replace };
}

/**
 * Run a mutation with a single pending flag and a typed error.
 * Returns [run, { pending, error, clear }].
 */
export function useAction(action) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const run = useCallback(async (...args) => {
    setPending(true); setError(null);
    try { return await action(...args); }
    catch (e) { setError(e); throw e; }
    finally { setPending(false); }
  }, [action]);
  return [run, { pending, error, clear: () => setError(null) }];
}

/** Keep focus inside a dialog, close on Escape and restore focus afterwards. */
export function useFocusTrap(ref, onClose) {
  useEffect(() => {
    const previous = document.activeElement;
    const focusables = () => Array.from(ref.current?.querySelectorAll(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])') ?? []);
    (ref.current?.querySelector("[data-autofocus]") ?? focusables()[0])?.focus();
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      if (e.key !== "Tab") return;
      const list = focusables(), first = list[0], last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); if (previous?.isConnected) previous.focus(); };
  }, [ref, onClose]);
}
