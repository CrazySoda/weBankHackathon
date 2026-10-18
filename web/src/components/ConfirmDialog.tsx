import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, X } from "lucide-react";

export type ConfirmOptions = {
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** destructive actions get a red confirm button */
  tone?: "danger" | "default";
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

function ConfirmDialog({ pending, onDone }: { pending: Pending; onDone: (ok: boolean) => void }) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    // destructive dialogs focus Cancel, so Enter never deletes by accident
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onDone(false);
      }
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button:not(:disabled)"));
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, [onDone]);

  const danger = pending.tone !== "default";
  return <div className="modal-overlay upload-overlay confirm-overlay" onClick={(event) => { if (event.target === event.currentTarget) onDone(false); }}>
    <section ref={dialogRef} className="upload-modal confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
      <header className="upload-modal-head">
        <div className={`upload-modal-icon ${danger ? "danger" : ""}`}><AlertTriangle size={18} /></div>
        <div><h2 id="confirm-title">{pending.title}</h2></div>
        <button className="icon-button" onClick={() => onDone(false)} aria-label="Close"><X size={18} /></button>
      </header>
      <div className="confirm-message" id="confirm-message">{pending.message}</div>
      <footer className="upload-modal-foot">
        <button ref={cancelRef} type="button" className="btn btn-secondary" onClick={() => onDone(false)}>{pending.cancelLabel ?? "Cancel"}</button>
        <button type="button" className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={() => onDone(true)}>{pending.confirmLabel ?? "Confirm"}</button>
      </footer>
    </section>
  </div>;
}

/**
 * In-app replacement for window.confirm:
 *   const [confirm, confirmDialog] = useConfirm();
 *   if (await confirm({ title, message })) { ... }
 * and render {confirmDialog} once in the component.
 */
export function useConfirm(): [(options: ConfirmOptions) => Promise<boolean>, ReactNode] {
  const [pending, setPending] = useState<Pending | null>(null);

  const confirm = useCallback((options: ConfirmOptions) => new Promise<boolean>((resolve) => {
    setPending((current) => {
      current?.resolve(false); // a newer question replaces an unanswered one
      return { ...options, resolve };
    });
  }), []);

  const done = useCallback((ok: boolean) => {
    setPending((current) => {
      current?.resolve(ok);
      return null;
    });
  }, []);

  return [confirm, pending ? createPortal(<ConfirmDialog pending={pending} onDone={done} />, document.body) : null];
}
