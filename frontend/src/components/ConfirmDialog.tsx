/**
 * App-styled replacement for window.confirm(), built on the native <dialog>
 * element (focus trapping and Esc-to-close come for free).
 *
 *   const [confirm, dialog] = useConfirm();
 *   if (await confirm({ title: "Delete post?", confirmLabel: "Delete", danger: true })) ...
 *   return <>{dialog}...</>
 */
import { useCallback, useEffect, useRef, useState, type ReactElement, type ReactNode } from "react";

interface Options {
  title: string;
  message?: string;
  confirmLabel?: string;
  danger?: boolean;
}

export function useConfirm(): [(options: Options) => Promise<boolean>, ReactElement] {
  const ref = useRef<HTMLDialogElement>(null);
  const resolver = useRef<((value: boolean) => void) | null>(null);
  const [options, setOptions] = useState<Options | null>(null);

  const confirm = useCallback((opts: Options) => {
    setOptions(opts);
    return new Promise<boolean>((resolve) => { resolver.current = resolve; });
  }, []);

  useEffect(() => {
    if (options && ref.current && !ref.current.open) ref.current.showModal();
  }, [options]);

  function finish(result: boolean) {
    resolver.current?.(result);
    resolver.current = null;
    ref.current?.close();
    setOptions(null);
  }

  const dialog = (
    <dialog
      ref={ref}
      className="dialog"
      onCancel={(e) => { e.preventDefault(); finish(false); }}
      onClick={(e) => { if (e.target === ref.current) finish(false); }} // backdrop click
      aria-labelledby="confirm-title"
    >
      {options && (
        <div className="dialog-body">
          <h2 id="confirm-title">{options.title}</h2>
          {options.message && <p className="muted">{options.message}</p>}
          <div className="row end">
            <button type="button" className="btn btn-secondary" onClick={() => finish(false)}>Cancel</button>
            <button
              type="button"
              className={`btn ${options.danger ? "btn-danger" : "btn-primary"}`}
              onClick={() => finish(true)}
              autoFocus
            >
              {options.confirmLabel ?? "Confirm"}
            </button>
          </div>
        </div>
      )}
    </dialog>
  );

  return [confirm, dialog];
}

/** A plain modal for forms (e.g. edit profile). */
export function Modal({ open, title, onClose, children }: {
  open: boolean; title: string; onClose: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog ref={ref} className="dialog" onCancel={(e) => { e.preventDefault(); onClose(); }} aria-labelledby="modal-title">
      {open && (
        <div className="dialog-body">
          <h2 id="modal-title">{title}</h2>
          {children}
        </div>
      )}
    </dialog>
  );
}
