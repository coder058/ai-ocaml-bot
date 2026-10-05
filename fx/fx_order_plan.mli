(** Pure OANDA request preparation, without HTTP, credentials or order authority.
    Initial scope: non-MT4 USD-home practice accounts. Callers must separately
    verify practice provenance, ownership, margin and durable reconciliation. *)
type side = Buy | Sell
type t = {
  request : Yojson.Safe.t;
  units : string;
  budget_usd : string;
  valuation_unit_usd : string;
  quote_time : string;
  conversion_poll_time : string;
  received_ns : int64;
}
val prepare :
  now_ns:int64 -> max_age_ns:int64 -> received_ns:int64 ->
  account:Yojson.Safe.t -> instrument:Yojson.Safe.t -> pricing:Yojson.Safe.t ->
  side:side -> budget_usd:string -> price_bound:string -> stop_price:string ->
  client_id:string -> (t, string) result
