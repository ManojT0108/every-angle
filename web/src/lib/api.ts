/**
 * The API contract, typed once.
 *
 * The invariant that matters: SEARCH and REEL read the PUBLISHED revision;
 * VERIFY works on the draft. The backend enforces it — these types just make it
 * hard to forget which one you are holding.
 */

export type EventType =
  | "goal"
  | "save"
  | "penalty"
  | "card"
  | "counterattack"
  | "celebration";
export type ProposalType = EventType | "none";
export type Confidence = "high" | "medium" | "low";
export type Decision = "pending" | "accepted" | "rejected";

export interface Match {
  video_id: string;
  duration: number;
  current_revision: number | null;
  collection: string | null;
  event_count: number;
}

/** A candidate window the detector opened — where the machine LOOKED. */
export interface Window {
  id: string;
  t_start: number;
  t_end: number;
  audio_peak: boolean;
  scene_cut: boolean;
  motion_peak: boolean;
  score: number;
}

/** A verified moment — what a human KEPT. `from_proposal: null` means human-added. */
export interface MomentEvent {
  id: string;
  from_proposal: string | null;
  t_start: number;
  t_end: number;
  type: EventType;
  caption: string;
  clip: string;
  team: string | null;
  player: string | null;
}

export interface Rejected {
  proposal_id: string;
  t_start: number;
  t_end: number;
  caption: string;
}

export interface Timeline {
  duration: number;
  windows: Window[];
  events: MomentEvent[];
  rejected: Rejected[];
}

export interface Proposal {
  id: string;
  t_start: number;
  t_end: number;
  type: ProposalType;
  confidence: Confidence;
  caption: string;
  status: Decision;
  frames: string[];
}

export interface SearchHit extends MomentEvent {
  score: number;
}

export interface Reel {
  url: string;
  duration: number;
  event_ids: string[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    // Surface what actually went wrong — a 503 from an unreachable Qdrant is a
    // very different problem from a 404, and the UI should say so.
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const api = {
  matches: () => req<Match[]>("/api/matches"),
  timeline: (id: string) => req<Timeline>(`/api/matches/${id}/timeline`),
  proposals: (id: string) => req<Proposal[]>(`/api/matches/${id}/proposals`),

  decide: (id: string, proposal_id: string, status: Exclude<Decision, "pending">) =>
    req<{ proposal_id: string; status: Decision }>(`/api/matches/${id}/decisions`, {
      method: "POST",
      body: JSON.stringify({ proposal_id, status }),
    }),

  addEvent: (
    id: string,
    body: { t_start: number; t_end: number; type: EventType; caption: string },
  ) =>
    req<MomentEvent>(`/api/matches/${id}/events`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  search: (id: string, q: string, limit = 8) =>
    req<SearchHit[]>(
      `/api/matches/${id}/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),

  reel: (id: string, event_ids: string[]) =>
    req<Reel>(`/api/matches/${id}/reel`, {
      method: "POST",
      body: JSON.stringify({ event_ids }),
    }),
};

/**
 * Media is served from the DATA ROOT, so a clip path stored in the manifest
 * ("clips/e-005.mp4") must be namespaced by its match to resolve.
 */
export function mediaUrl(videoId: string, relativePath: string): string {
  return `/media/${videoId}/${relativePath.replace(/^\/+/, "")}`;
}

/** 2705 -> "45:05". Match clock, not wall clock. */
export function timecode(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function isHumanAdded(e: { from_proposal: string | null }): boolean {
  return e.from_proposal === null;
}
