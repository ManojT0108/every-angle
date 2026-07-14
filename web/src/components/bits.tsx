import type { ReactNode } from "react";
import { timecode } from "../lib/api";

/**
 * Provenance, made visible.
 *
 * Sodium = the machine proposed this. Chalk = a human stood behind it. This is
 * the honest heart of the product, so it gets a first-class component rather
 * than being buried in a tooltip.
 */
export function Provenance({ human }: { human: boolean }) {
  return human ? (
    <span className="chip border-chalk-faint text-chalk">Human-added</span>
  ) : (
    <span className="chip border-sodium/45 text-sodium">AI-proposed</span>
  );
}

export function TypeChip({ type }: { type: string }) {
  const goal = type === "goal";
  return (
    <span
      className={
        goal
          ? "chip border-sodium bg-sodium font-bold text-sodium-ink"
          : "chip"
      }
    >
      {type}
    </span>
  );
}

export function Figure({
  label,
  value,
  unit,
  hero,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hero?: boolean;
}) {
  return (
    <div className="bg-ink-800 px-4 py-3.5">
      <div className="eyebrow">{label}</div>
      <div
        className={`display tnum mt-1 text-[26px] leading-none ${
          hero ? "text-sodium" : "text-chalk"
        }`}
      >
        {value}
        {unit && (
          <small className="ml-1 text-[13px] font-normal tracking-normal text-chalk-faint">
            {unit}
          </small>
        )}
      </div>
    </div>
  );
}

export function Figures({ children }: { children: ReactNode }) {
  return (
    <div className="my-6 grid gap-px border border-line bg-line [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
      {children}
    </div>
  );
}

export function Button({
  children,
  onClick,
  tone = "default",
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: "default" | "keep" | "drop" | "primary";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const tones = {
    default: "border-line text-chalk-dim hover:border-chalk-faint hover:text-chalk",
    keep: "border-turf text-turf hover:bg-turf hover:text-ink-900",
    drop: "border-line text-chalk-dim hover:border-tally hover:text-tally",
    primary: "border-sodium bg-sodium text-sodium-ink hover:brightness-110",
  }[tone];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`cursor-pointer border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.1em] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${tones}`}
    >
      {children}
    </button>
  );
}

/** A clip thumbnail that plays on hover — cheap, and it makes the list feel alive. */
export function ClipThumb({
  src,
  t,
  poster,
}: {
  src?: string;
  t: number;
  poster?: string;
}) {
  return (
    <div className="relative aspect-video w-[132px] shrink-0 overflow-hidden border border-line-soft bg-ink-700">
      {src ? (
        <video
          src={src}
          poster={poster}
          muted
          playsInline
          preload="metadata"
          className="size-full object-cover"
          onMouseEnter={(e) => void e.currentTarget.play().catch(() => {})}
          onMouseLeave={(e) => {
            e.currentTarget.pause();
            e.currentTarget.currentTime = 0;
          }}
        />
      ) : (
        <div className="pitch-bg size-full" />
      )}
      <span className="tnum absolute bottom-1 right-1 bg-black/60 px-1 font-mono text-[9px] text-white">
        {timecode(t)}
      </span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="border border-dashed border-line px-6 py-14 text-center text-chalk-faint">
      {children}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="border border-tally/40 bg-tally/5 px-4 py-3 text-[13px] text-chalk-dim">
      {children}
    </div>
  );
}
