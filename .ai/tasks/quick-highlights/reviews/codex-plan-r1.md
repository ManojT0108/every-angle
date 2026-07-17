Verified-first is the right default for a judged demo. The unverified mode should not be the headline—or ship before the deadline.

- **P1 — lines 18–22:** The algorithm does not deduplicate incidents. Real manifests contain overlapping windows for the same goal and celebration; the current match-002 manifest would select several replays of one goal while potentially excluding the trophy because `celebration` ranks last.  
  **Fix:** Cluster overlapping/near-adjacent events into incidents, choose one representative per incident, and reserve one terminal celebration slot when available.

- **P2 — lines 18–24:** “Game-changer,” “decisive goal,” close-chance severity, and card severity are not structured manifest fields. A literal implementation would guess from captions, and it currently ranks a routine yellow card above a major save.  
  **Fix:** For v1, rank only available types: `goal > penalty > save > counterattack > card`, treat all goals equally, and handle one final-whistle/trophy celebration separately.

- **P2 — lines 22 and 39–40:** “Top ~8 or ~90 seconds” is ambiguous; eight existing 30-second clips produce a four-minute reel.  
  **Fix:** Define both limits: maximum eight incidents and 90 seconds, skipping candidates that would exceed the duration budget.

- **P2 — lines 23–29 and 41:** Runtime AI ranking, “why it matters,” and an unverified mode add failure paths and dilute the verified-first story while deployment remains unfinished.  
  **Fix:** Ship a deterministic client-side Quick Highlights button over the promoted manifest; move blurbs and unverified mode explicitly out of deadline scope, with zero events disabling the button and a near-empty pool using all available events.

REQUEST_CHANGES