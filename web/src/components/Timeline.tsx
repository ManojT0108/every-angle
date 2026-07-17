import { useState } from "react";
import {
  isHumanAdded,
  mediaUrl,
  timecode,
  type MomentEvent,
  type Timeline as TL,
} from "../lib/api";
import {
  DEFAULT_TIMELINE_ZOOM,
  positionTimelineEvents,
  timelineEventLabel,
  timelineTicks,
  TIMELINE_CANVAS_PADDING,
  TIMELINE_ZOOM_LEVELS,
} from "../lib/timeline";
import { ClipModal } from "./bits";

const EVENT_LANE_HEIGHT = 30;

/** The match timeline: where the detector looked and what a human kept. */
export function Timeline({
  matchId,
  data,
  onSeek,
  activeId,
}: {
  matchId: string;
  data: TL;
  onSeek?: (t: number) => void;
  activeId?: string | null;
}) {
  const [playing, setPlaying] = useState<MomentEvent | null>(null);
  const [zoomIndex, setZoomIndex] = useState(
    TIMELINE_ZOOM_LEVELS.indexOf(DEFAULT_TIMELINE_ZOOM),
  );

  return (
    <TimelineView
      matchId={matchId}
      data={data}
      onSeek={onSeek}
      activeId={activeId}
      playing={playing}
      onPlay={setPlaying}
      onClose={() => setPlaying(null)}
      pixelsPerMinute={TIMELINE_ZOOM_LEVELS[zoomIndex]}
      onZoomOut={() => setZoomIndex((current) => Math.max(0, current - 1))}
      onZoomIn={() =>
        setZoomIndex((current) =>
          Math.min(TIMELINE_ZOOM_LEVELS.length - 1, current + 1),
        )
      }
    />
  );
}

export function TimelineView({
  matchId,
  data,
  onSeek,
  activeId,
  playing,
  onPlay,
  onClose,
  pixelsPerMinute = DEFAULT_TIMELINE_ZOOM,
  onZoomIn,
  onZoomOut,
}: {
  matchId: string;
  data: TL;
  onSeek?: (t: number) => void;
  activeId?: string | null;
  playing: MomentEvent | null;
  onPlay: (event: MomentEvent) => void;
  onClose: () => void;
  pixelsPerMinute?: number;
  onZoomIn?: () => void;
  onZoomOut?: () => void;
}) {
  const { duration, windows, events, rejected } = data;
  const positionedEvents = positionTimelineEvents(events, pixelsPerMinute);
  const eventLaneCount = Math.max(
    1,
    ...positionedEvents.map(({ lane }) => lane + 1),
  );
  const eventAreaHeight = eventLaneCount * EVENT_LANE_HEIGHT + 10;
  const rejectedTop = eventAreaHeight + 8;
  const candidateTop = rejectedTop + 23;
  const ticksTop = candidateTop + 25;
  const canvasHeight = ticksTop + 24;
  const scaledDuration = (Math.max(0, duration) / 60) * pixelsPerMinute;
  const canvasWidth = Math.max(
    2 * TIMELINE_CANVAS_PADDING,
    scaledDuration + 2 * TIMELINE_CANVAS_PADDING,
  );
  const x = (t: number) =>
    TIMELINE_CANVAS_PADDING +
    (Math.min(Math.max(0, t), Math.max(0, duration)) / 60) * pixelsPerMinute;
  const rangeWidth = (start: number, end: number) =>
    Math.max(1, ((Math.max(start, end) - Math.min(start, end)) / 60) * pixelsPerMinute);
  const reviewed = windows.reduce((total, window) => {
    return total + Math.max(0, window.t_end - window.t_start);
  }, 0);
  const ticks = timelineTicks(duration, pixelsPerMinute);
  const showZoomControls = onZoomIn !== undefined && onZoomOut !== undefined;
  const zoomLevel =
    TIMELINE_ZOOM_LEVELS.findIndex((level) => level === pixelsPerMinute) + 1;

  return (
    <section aria-label="Match timeline" className="mt-7">
      <header className="mb-2.5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="eyebrow">Match timeline</span>
          {showZoomControls && (
            <div className="mt-2 flex items-center gap-2">
              <button
                type="button"
                aria-label="Zoom timeline out"
                disabled={pixelsPerMinute === TIMELINE_ZOOM_LEVELS[0]}
                onClick={onZoomOut}
                className="size-7 cursor-pointer border border-line font-mono text-[14px] text-chalk-dim disabled:cursor-not-allowed disabled:opacity-35"
              >
                −
              </button>
              <span className="tnum min-w-28 text-center font-mono text-[10px] text-chalk-faint">
                Zoom {zoomLevel} of {TIMELINE_ZOOM_LEVELS.length} · {pixelsPerMinute}
                px/min
              </span>
              <button
                type="button"
                aria-label="Zoom timeline in"
                disabled={
                  pixelsPerMinute ===
                  TIMELINE_ZOOM_LEVELS[TIMELINE_ZOOM_LEVELS.length - 1]
                }
                onClick={onZoomIn}
                className="size-7 cursor-pointer border border-line font-mono text-[14px] text-chalk-dim disabled:cursor-not-allowed disabled:opacity-35"
              >
                +
              </button>
            </div>
          )}
        </div>
        <div
          aria-label="Timeline legend"
          className="flex max-w-full flex-wrap gap-x-3 gap-y-1 border-l border-line pl-3 font-mono text-[9.5px] tracking-wide text-chalk-faint"
        >
          <Key swatch="bg-chalk" label="Human-added" />
          <Key swatch="bg-sodium" label="AI-proposed" />
          <Key swatch="border border-dashed border-chalk-faint" label="Rejected" />
          <Key swatch="bg-sodium-dim" label="Candidate window" />
        </div>
      </header>

      <div className="mb-1.5 flex items-center justify-end gap-2 font-mono text-[9px] uppercase tracking-[0.12em] text-chalk-faint">
        <span>Scroll to explore</span>
        <span aria-hidden className="text-sodium">
          →
        </span>
      </div>

      <div
        role="region"
        aria-label="Scrollable match timeline"
        tabIndex={0}
        className="timeline-scroll max-w-full overflow-x-auto border border-line bg-ink-800"
      >
        <div
          className="relative min-w-full"
          data-pixels-per-minute={pixelsPerMinute}
          data-timeline-canvas
          style={{ width: `${canvasWidth}px`, height: `${canvasHeight}px` }}
        >
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-35"
            style={{
              background:
                "repeating-linear-gradient(90deg, transparent 0 44px, color-mix(in srgb, var(--color-turf) 7%, transparent) 44px 88px)",
            }}
          />

          <div
            aria-hidden
            className="absolute h-px bg-line"
            style={{
              left: TIMELINE_CANVAS_PADDING,
              top: eventAreaHeight,
              width: scaledDuration,
            }}
          />

          {positionedEvents.map(({ event, hitboxWidth, lane, x: eventX }) => {
            const human = isHumanAdded(event);
            const active = activeId === event.id;
            const className = `absolute flex h-6 -translate-x-1/2 items-center justify-center gap-1 border bg-ink-800 px-1.5 font-mono text-[9px] uppercase tracking-wide ${
              human ? "border-chalk text-chalk" : "border-sodium text-sodium"
            } ${active ? "ring-2 ring-sodium" : ""}`;
            const mark = (
              <>
                <span
                  aria-hidden
                  className={`size-1.5 shrink-0 ${human ? "bg-chalk" : "bg-sodium"}`}
                />
                <span className="truncate">{timelineEventLabel(event)}</span>
              </>
            );
            const style = {
              left: eventX,
              top: 5 + lane * EVENT_LANE_HEIGHT,
              width: hitboxWidth,
            };

            return event.clip ? (
              <button
                type="button"
                key={event.id}
                data-event-lane={lane}
                onClick={() => {
                  onSeek?.(event.t_start);
                  onPlay(event);
                }}
                style={style}
                title={event.caption}
                className={`${className} cursor-pointer hover:bg-ink-700`}
                aria-label={`Play ${event.type} clip at ${timecode(event.t_start)}`}
              >
                {mark}
              </button>
            ) : (
              <div
                key={event.id}
                data-event-lane={lane}
                style={style}
                title={event.caption}
                className={`${className} cursor-default opacity-70`}
              >
                {mark}
              </div>
            );
          })}

          <div
            className="absolute font-mono text-[9px] text-chalk-faint"
            style={{ left: TIMELINE_CANVAS_PADDING, top: rejectedTop - 11 }}
          >
            Rejected
          </div>
          {rejected.map((proposal) => (
            <div
              key={proposal.proposal_id}
              data-timeline-lane="rejected"
              style={{
                left: x(proposal.t_start),
                top: rejectedTop,
                width: rangeWidth(proposal.t_start, proposal.t_end),
              }}
              title={`Rejected by a human — ${proposal.caption}`}
              className="absolute h-2 border border-dashed border-chalk-faint opacity-70"
            />
          ))}

          <div
            className="absolute font-mono text-[9px] text-chalk-faint"
            style={{ left: TIMELINE_CANVAS_PADDING, top: candidateTop - 11 }}
          >
            Candidate windows
          </div>
          {windows.map((window) => {
            const cues = [window.motion_peak, window.audio_peak, window.scene_cut].filter(
              Boolean,
            ).length;
            return (
              <div
                key={window.id}
                data-timeline-lane="candidate"
                style={{
                  left: x(window.t_start),
                  top: candidateTop,
                  width: rangeWidth(window.t_start, window.t_end),
                  height: 4 + cues * 2,
                }}
                title={`${window.id} · ${timecode(window.t_start)}–${timecode(
                  window.t_end,
                )} · ${
                  [
                    window.motion_peak && "motion",
                    window.audio_peak && "crowd audio",
                    window.scene_cut && "scene cut",
                  ]
                    .filter(Boolean)
                    .join(" + ") || "no cue"
                }`}
                className="absolute bg-sodium-dim"
              />
            );
          })}

          <div className="tnum absolute inset-x-0 font-mono text-[9px] tracking-wide text-chalk-faint" style={{ top: ticksTop }}>
            {ticks.map((tick) => (
              <span
                key={tick}
                style={{ left: x(tick) }}
                className={`absolute ${
                  tick === 0
                    ? ""
                    : tick === duration
                      ? "-translate-x-full"
                      : "-translate-x-1/2"
                }`}
              >
                {timecode(tick)}
              </span>
            ))}
          </div>
        </div>
      </div>

      <ClipModal
        src={playing?.clip ? mediaUrl(matchId, playing.clip) : undefined}
        t={playing?.t_start ?? 0}
        open={Boolean(playing?.clip)}
        onClose={onClose}
      />

      <p className="mt-3.5 max-w-[72ch] text-[12.5px] text-chalk-faint">
        Scroll horizontally and zoom to explore the match. Candidate bars show where the
        detector <b className="font-semibold text-chalk-dim">looked</b> —{" "}
        <span className="tnum">{windows.length}</span> windows,{" "}
        <span className="tnum">{timecode(reviewed)}</span> of{" "}
        <span className="tnum">{timecode(duration)}</span>. Verified moment buttons play every
        available clip; rejected ranges remain visible as human-reviewed provenance.
      </p>
    </section>
  );
}

function Key({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <i className={`inline-block size-2 rounded-[1px] ${swatch}`} />
      {label}
    </span>
  );
}
