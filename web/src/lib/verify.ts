import type { QueryClient } from "@tanstack/react-query";
import type { Proposal } from "./api";

export function judgedProposals(proposals: Proposal[]): Proposal[] {
  return proposals.filter((proposal) => proposal.status !== "pending" && proposal.type !== "none");
}

export function invalidateReviewQueries(
  queryClient: Pick<QueryClient, "invalidateQueries">,
  matchId: string,
): void {
  void queryClient.invalidateQueries({ queryKey: ["proposals", matchId] });
  void queryClient.invalidateQueries({ queryKey: ["timeline", matchId] });
  void queryClient.invalidateQueries({ queryKey: ["search", matchId] });
}
