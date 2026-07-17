import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  api,
  timecode,
  type EventType,
  type Proposal,
  type ProposalType,
} from "../lib/api";
import { invalidateReviewQueries, judgedProposals } from "../lib/verify";
import { Button, ClipThumb, Empty, ErrorNote, TypeChip } from "../components/bits";

/**
 * Review — the human-in-the-loop step, and the honest heart of the product.
 *
 * We show playable footage of the proposed window, with the frames the model
 * actually saw as a fallback when a clip is unavailable. Nothing is hidden
 * behind a confidence score.
 */
export function Verify({ matchId }: { matchId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["proposals", matchId],
    queryFn: () => api.proposals(matchId),
  });
  const { data: capabilities } = useQuery({
    queryKey: ["capabilities", matchId],
    queryFn: () => api.capabilities(matchId),
  });

  const decide = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "accepted" | "rejected" }) =>
      api.decide(matchId, id, status),
    onSuccess: () => invalidateReviewQueries(qc, matchId),
  });

  const edit = useMutation({
    mutationFn: ({
      id,
      caption,
      type,
    }: {
      id: string;
      caption: string;
      type: ProposalType;
    }) => api.editProposal(matchId, id, { caption, type }),
    onSuccess: () => invalidateReviewQueries(qc, matchId),
  });

  if (error) return <ErrorNote>Could not load proposals — {(error as Error).message}</ErrorNote>;
  if (isLoading) return <Empty>Loading proposals…</Empty>;

  const pending = (data ?? []).filter((p) => p.status === "pending" && p.type !== "none");
  const settled = judgedProposals(data ?? []);
  const dismissed = (data ?? []).filter((p) => p.status === "pending" && p.type === "none").length;

  return (
    <div className="space-y-8">
      <div>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
          <span className="eyebrow">Awaiting your review</span>
          <span className="tnum font-mono text-[11px] text-chalk-faint">
            {dismissed} windows dismissed as ordinary play
          </span>
        </div>

        {pending.length === 0 ? (
          <Empty>Every proposal has been reviewed.</Empty>
        ) : (
          <div className="grid gap-px border border-line bg-line">
            {pending.map((p) => (
              <ProposalCard
                key={p.id}
                p={p}
                busy={decide.isPending || edit.isPending}
                onDecide={(status) => decide.mutate({ id: p.id, status })}
                onEdit={(caption, type) =>
                  edit.mutateAsync({ id: p.id, caption, type })
                }
              />
            ))}
          </div>
        )}
      </div>

      {decide.error && <ErrorNote>{(decide.error as Error).message}</ErrorNote>}
      {edit.error && <ErrorNote>{(edit.error as Error).message}</ErrorNote>}

      {capabilities?.source_video_available && <AddMoment matchId={matchId} />}

      {settled.length > 0 && (
        <div>
          <div className="eyebrow mb-3">Reviewed</div>
          <div className="grid gap-px border border-line bg-line">
            {settled.map((p) => (
              <article key={p.id} className="bg-ink-800 px-4 py-3 text-[13px]">
                <div className="flex items-center gap-4">
                  <span
                    className={`chip ${
                      p.status === "accepted"
                        ? "border-turf/50 text-turf"
                        : "border-line text-chalk-faint"
                    }`}
                  >
                    {p.status}
                  </span>
                  <span className="tnum font-mono text-[11px] text-chalk-faint">
                    {timecode(p.t_start)}
                  </span>
                  <span
                    className={`min-w-0 flex-1 truncate ${
                      p.status === "rejected"
                        ? "text-chalk-faint line-through"
                        : "text-chalk-dim"
                    }`}
                  >
                    {p.caption}
                  </span>
                  {p.status === "accepted" && (
                    <Button
                      tone="drop"
                      disabled={decide.isPending}
                      onClick={() => decide.mutate({ id: p.id, status: "rejected" })}
                    >
                      Undo
                    </Button>
                  )}
                </div>
                <ProposalEditor
                  p={p}
                  busy={decide.isPending || edit.isPending}
                  onSave={(caption, type) =>
                    edit.mutateAsync({ id: p.id, caption, type })
                  }
                />
                <ProposalMedia p={p} />
              </article>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ProposalCard({
  p,
  onDecide,
  onEdit,
  busy,
}: {
  p: Proposal;
  onDecide: (s: "accepted" | "rejected") => void;
  onEdit: (caption: string, type: ProposalType) => Promise<unknown>;
  busy: boolean;
}) {
  return (
    <article className="bg-ink-800 p-4">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <p className="mb-2 text-[14px] leading-relaxed">{p.caption}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            <TypeChip type={p.type} />
            <span className="chip border-sodium/45 text-sodium">AI-proposed</span>
            <span className="chip text-chalk-faint">{p.confidence} confidence</span>
            <span className="chip tnum">
              {timecode(p.t_start)}–{timecode(p.t_end)}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button tone="keep" disabled={busy} onClick={() => onDecide("accepted")}>
            Keep
          </Button>
          <Button tone="drop" disabled={busy} onClick={() => onDecide("rejected")}>
            Reject
          </Button>
        </div>
      </div>

      <ProposalEditor p={p} busy={busy} onSave={onEdit} />
      <ProposalMedia p={p} />
    </article>
  );
}

function ProposalEditor({
  p,
  busy,
  onSave,
}: {
  p: Proposal;
  busy: boolean;
  onSave: (caption: string, type: ProposalType) => Promise<unknown>;
}) {
  const [editing, setEditing] = useState(false);
  const [caption, setCaption] = useState(p.caption);
  const [type, setType] = useState<ProposalType>(p.type);

  if (!editing) {
    return (
      <div className="mt-3">
        <Button
          disabled={busy}
          onClick={() => {
            setCaption(p.caption);
            setType(p.type);
            setEditing(true);
          }}
        >
          Edit
        </Button>
      </div>
    );
  }

  return (
    <ProposalEditForm
      caption={caption}
      type={type}
      busy={busy}
      onCaptionChange={setCaption}
      onTypeChange={setType}
      onSave={() => {
        void onSave(caption.trim(), type)
          .then(() => setEditing(false))
          .catch(() => {});
      }}
      onCancel={() => setEditing(false)}
    />
  );
}

export function ProposalEditForm({
  caption,
  type,
  busy,
  onCaptionChange,
  onTypeChange,
  onSave,
  onCancel,
}: {
  caption: string;
  type: ProposalType;
  busy: boolean;
  onCaptionChange: (caption: string) => void;
  onTypeChange: (type: ProposalType) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <form
      className="mt-3 space-y-3 border border-line bg-ink-900 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <Field label="Caption">
        <textarea
          value={caption}
          onChange={(event) => onCaptionChange(event.target.value)}
          required
          rows={2}
          className="w-full resize-y border border-line bg-ink-800 px-3 py-2 text-[14px] outline-none focus:border-sodium"
        />
      </Field>
      <Field label="Type">
        <select
          value={type}
          onChange={(event) => onTypeChange(event.target.value as ProposalType)}
          className="border border-line bg-ink-800 px-2 py-1.5 text-[13px] outline-none focus:border-sodium"
        >
          {["goal", "save", "penalty", "card", "counterattack", "celebration", "none"].map(
            (value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ),
          )}
        </select>
      </Field>
      <div className="flex gap-2">
        <Button type="submit" tone="primary" disabled={busy || !caption.trim()}>
          {busy ? "Saving…" : "Save"}
        </Button>
        <Button disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function ProposalMedia({ p }: { p: Proposal }) {
  const tight = p.frames.filter((f) => f.includes("tight"));
  const wide = p.frames.filter((f) => f.includes("wide"));
  const strip = tight.length || wide.length ? [...tight, ...wide] : p.frames;

  if (p.clip) {
    return (
      <div className="mt-3.5">
        <ClipThumb src={p.clip} poster={p.frames[0]} t={p.t_start} />
      </div>
    );
  }

  return (
    <>
      {/* the evidence — exactly what the model was shown, in order */}
      {strip.length > 0 && (
        <div className="mt-3.5">
          <div className="eyebrow mb-1.5">
            What the model saw — {tight.length} tight (tracking the ball), {wide.length} wide
            (what happened next)
          </div>
          <div className="flex gap-1 overflow-x-auto pb-1">
            {strip.map((src, i) => (
              <img
                key={src}
                src={src}
                alt={`Evidence frame ${i + 1}`}
                loading="lazy"
                className={`h-24 w-auto shrink-0 border object-cover ${
                  src.includes("wide") ? "border-line-soft opacity-80" : "border-sodium/30"
                }`}
              />
            ))}
          </div>
        </div>
      )}
    </>
  );
}

/** The goal the AI missed gets in here — and flows onward identically. */
function AddMoment({ matchId }: { matchId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState("39:26");
  const [len, setLen] = useState("18");
  const [type, setType] = useState<EventType>("goal");
  const [caption, setCaption] = useState("");

  const add = useMutation({
    mutationFn: () => {
      const [m, s] = start.split(":").map(Number);
      const t = (m || 0) * 60 + (s || 0);
      return api.addEvent(matchId, {
        t_start: t,
        t_end: t + Number(len || 15),
        type,
        caption,
      });
    },
    onSuccess: () => {
      setOpen(false);
      setCaption("");
      invalidateReviewQueries(qc, matchId);
    },
  });

  if (!open) {
    return (
      <div className="flex items-center justify-between border border-dashed border-line px-4 py-3.5">
        <p className="max-w-[62ch] text-[13px] text-chalk-faint">
          The AI missed a goal at 39:26. A human can add it — and it flows into search and the
          reel exactly like an AI-proposed one, because the manifest is the source of truth, not
          the model.
        </p>
        <Button tone="keep" onClick={() => setOpen(true)}>
          + Add moment
        </Button>
      </div>
    );
  }

  return (
    <form
      className="space-y-3 border border-line bg-ink-800 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <div className="eyebrow">Add a moment the AI missed</div>
      <div className="flex flex-wrap gap-3">
        <Field label="Start (m:ss)">
          <input
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="tnum w-24 border border-line bg-ink-900 px-2 py-1.5 font-mono text-[13px] outline-none focus:border-sodium"
          />
        </Field>
        <Field label="Length (s)">
          <input
            value={len}
            onChange={(e) => setLen(e.target.value)}
            className="tnum w-20 border border-line bg-ink-900 px-2 py-1.5 font-mono text-[13px] outline-none focus:border-sodium"
          />
        </Field>
        <Field label="Type">
          <select
            value={type}
            onChange={(e) => setType(e.target.value as EventType)}
            className="border border-line bg-ink-900 px-2 py-1.5 text-[13px] outline-none focus:border-sodium"
          >
            {["goal", "save", "penalty", "card", "counterattack", "celebration"].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="What happened (this is what search will match on)">
        <input
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          required
          placeholder="goal from a scramble in the right-side box, keeper beaten at close range"
          className="w-full border border-line bg-ink-900 px-3 py-2 text-[14px] outline-none placeholder:text-chalk-faint focus:border-sodium"
        />
      </Field>
      {add.error && <ErrorNote>{(add.error as Error).message}</ErrorNote>}
      <div className="flex gap-2">
        <Button type="submit" tone="primary" disabled={add.isPending}>
          {add.isPending ? "Adding…" : "Add moment"}
        </Button>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="eyebrow mb-1 block">{label}</span>
      {children}
    </label>
  );
}
