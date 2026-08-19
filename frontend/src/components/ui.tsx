/** Small presentational primitives shared across screens. */

import type { ReactNode } from "react";

import { initials } from "@/lib/format";

export function Screen({ children }: { children: ReactNode }) {
  return <main className="screen">{children}</main>;
}

export function Card({
  children,
  onClick,
  tight,
}: {
  children: ReactNode;
  onClick?: () => void;
  tight?: boolean;
}) {
  const className = `card${tight ? " card-tight" : ""}${onClick ? " card-interactive" : ""}`;
  if (onClick) {
    return (
      <button type="button" className={className} style={{ textAlign: "left", width: "100%" }} onClick={onClick}>
        {children}
      </button>
    );
  }
  return <div className={className}>{children}</div>;
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="row-between">
      <span className="section-title">{children}</span>
      {action}
    </div>
  );
}

export function Avatar({
  src,
  name,
  size = "md",
}: {
  src?: string | null;
  name: string;
  size?: "md" | "lg";
}) {
  const className = size === "lg" ? "avatar avatar-lg" : "avatar";
  if (src) return <img className={className} src={src} alt={name} loading="lazy" />;
  return <div className={className}>{initials(name) || "?"}</div>;
}

export function Empty({ glyph, title, hint }: { glyph: string; title: string; hint?: string }) {
  return (
    <div className="empty">
      <span className="glyph">{glyph}</span>
      <strong>{title}</strong>
      {hint ? <span className="faint">{hint}</span> : null}
    </div>
  );
}

export function Skeleton({ height = 72, count = 3 }: { height?: number; count?: number }) {
  return (
    <div className="stack">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="skeleton" style={{ height }} />
      ))}
    </div>
  );
}

export function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} />
      <div className="sheet" role="dialog" aria-modal="true">
        <div className="sheet-handle" />
        {title ? <h2 style={{ marginBottom: "var(--sp-4)" }}>{title}</h2> : null}
        {children}
      </div>
    </>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "win" | "dim" }) {
  return (
    <div className="stack" style={{ gap: 2 }}>
      <span className="faint">{label}</span>
      <strong
        className="num"
        style={{ fontSize: 17, color: tone === "win" ? "var(--win)" : tone === "dim" ? "var(--text-dim)" : undefined }}
      >
        {value}
      </strong>
    </div>
  );
}

export function Bar({ progress }: { progress: number }) {
  return (
    <div className="bar">
      <span style={{ width: `${Math.min(Math.max(progress, 0), 1) * 100}%` }} />
    </div>
  );
}

export function Badge({ status }: { status: string }) {
  const tone =
    status === "waiting" || status === "starting"
      ? "badge-wait"
      : status === "spinning" || status === "active"
        ? "badge-live"
        : "badge-done";
  return <span className={`badge ${tone}`}>{status.replace(/_/g, " ")}</span>;
}
