import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface UploadTooltipProps {
  label: string;
  content: string;
  className?: string;
  children: ReactNode;
}

export function UploadTooltip({ label, content, className = "", children }: UploadTooltipProps) {
  const id = useId();
  const anchorRef = useRef<HTMLSpanElement>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number; above: boolean } | null>(null);

  const cancelHide = () => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = null;
  };

  const hideSoon = () => {
    cancelHide();
    hideTimer.current = setTimeout(() => setPosition(null), 180);
  };

  const place = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const width = Math.min(300, window.innerWidth - 24);
    const left = Math.max(12, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 12));
    const above = rect.bottom + 128 > window.innerHeight;
    setPosition({ left, top: above ? rect.top - 8 : rect.bottom + 8, above });
  }, []);

  useEffect(() => {
    if (!position) return;
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [place, position]);

  return <>
    <span
      ref={anchorRef}
      className={`upload-help ${className}`}
      tabIndex={0}
      aria-label={label}
      aria-describedby={position ? id : undefined}
      onMouseEnter={place}
      onMouseLeave={hideSoon}
      onFocus={place}
      onBlur={() => setPosition(null)}
    >{children}</span>
    {position && createPortal(
      <span
        id={id}
        role="tooltip"
        className={`upload-tooltip-portal ${position.above ? "above" : "below"}`}
        style={{ left: position.left, top: position.top }}
        onMouseEnter={cancelHide}
        onMouseLeave={hideSoon}
      >{content}</span>,
      document.body,
    )}
  </>;
}
