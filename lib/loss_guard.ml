(* New-exposure guard for policies whose measured after-cost results were
   negative (docs/PROFITABILITY-REVIEW.md). Buying requires naming the policy
   in ALLOW_NEGATIVE_EDGE_POLICY (comma-separated). Exits, reconciliation and
   monitoring are never affected, so owned positions can always be closed. *)
let quote_cross = "quote_cross_30s_v1"
let candle_confluence = "trend_candle_confluence_v1"
let allows policy =
  match Sys.getenv_opt "ALLOW_NEGATIVE_EDGE_POLICY" with
  | None -> false
  | Some value -> List.mem policy (List.map String.trim (String.split_on_char ',' value))
let reason policy =
  policy ^ " lost after fees in recorded audits; set ALLOW_NEGATIVE_EDGE_POLICY=" ^ policy ^ " to buy anyway"
