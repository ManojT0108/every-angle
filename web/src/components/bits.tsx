import { useEffect, useState, type ReactNode } from "react";
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
      className={`min-h-9 cursor-pointer whitespace-nowrap border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.1em] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${tones}`}
    >
      {children}
    </button>
  );
}

/** A compact clip preview with a full-size player on demand. */
export function ClipThumb({
  src,
  t,
  poster,
}: {
  src?: string;
  t: number;
  poster?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <ClipThumbPlayer
      src={src}
      t={t}
      poster={poster}
      open={open}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
    />
  );
}

export function ClipThumbPlayer({
  src,
  t,
  poster,
  open,
  onOpen,
  onClose,
}: {
  src?: string;
  t: number;
  poster?: string;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}) {
  const label = `Play clip at ${timecode(t)}`;

  return (
    <>
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
        {src && (
          <button
            type="button"
            aria-label={label}
            onClick={onOpen}
            className="absolute inset-0 flex cursor-pointer items-center justify-center bg-black/15 text-white transition-colors hover:bg-black/35"
          >
            <span
              aria-hidden="true"
              className="flex size-9 items-center justify-center rounded-full border border-white/80 bg-black/60 pl-0.5 text-[15px]"
            >
              ▶
            </span>
          </button>
        )}
        <span className="tnum pointer-events-none absolute bottom-1 right-1 bg-black/60 px-1 font-mono text-[9px] text-white">
          {timecode(t)}
        </span>
      </div>

      <ClipModal
        src={src}
        t={t}
        poster={poster}
        open={open}
        onClose={onClose}
      />
    </>
  );
}

/** A controlled full-size clip player shared by any compact trigger. */
export function ClipModal({
  src,
  t,
  poster,
  open,
  onClose,
}: {
  src?: string;
  t: number;
  poster?: string;
  open: boolean;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  if (!src || !open) return null;

  return (
    <ClipModalView src={src} t={t} poster={poster} onClose={onClose} />
  );
}

export function ClipModalView({
  src,
  t,
  poster,
  onClose,
}: {
  src: string;
  t: number;
  poster?: string;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Video clip at ${timecode(t)}`}
      onClick={onClose}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/85 p-3 sm:p-6"
    >
      <div
        className="relative w-full max-w-5xl"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          aria-label="Close clip"
          onClick={onClose}
          className="absolute -right-2 -top-10 cursor-pointer px-2 text-[28px] leading-none text-white"
        >
          ×
        </button>
        <video
          src={src}
          poster={poster}
          controls
          autoPlay
          className="max-h-[85vh] w-full border border-line bg-black"
        />
      </div>
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
