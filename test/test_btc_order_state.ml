open Paper_market
let check name value = if not value then failwith name
let unwrap = function Ok value -> value | Error message -> failwith message
(* SOURCE: synthetic IDs, quantities and lifecycle failures test durable
   reconciliation; they are not orders or market outcomes. *)
let id="jsbotbtcbuySynthetic"
let order = `Assoc ["client_order_id",`String id; "symbol",`String "BTCUSD";
  "side",`String "buy"; "status",`String "canceled";
  "qty",`String "0.001000000"; "filled_qty",`String "0.000500000"]
let replace key value = function
  | `Assoc fields -> `Assoc ((key,value)::List.remove_assoc key fields)
  | _ -> assert false
let () =
  let intent=unwrap (Btc_order_state.parse_pending (id |> fun id -> "buy " ^ id ^ " 0.001000000")) in
  List.iter (fun legacy -> check "compatible durable formats"
    (Result.is_ok (Btc_order_state.parse_pending legacy))) ["buy "^id; "buy "^id^" 0.001000000"];
  check "partial canceled fill is real" ((unwrap (Btc_order_state.validate intent order)).filled = 500_000L);
  List.iter (fun (key,value) -> check "malformed broker result rejected"
    (Result.is_error (Btc_order_state.validate intent (replace key value order))))
    ["symbol",`String "AAPL"; "side",`String "sell"; "client_order_id",`String "unrelated";
     "qty",`String "0.002"; "filled_qty",`Null; "filled_qty",`String "NaN";
     "filled_qty",`String "-1"; "filled_qty",`String "0.0010000001";
     "filled_qty",`String "0.002"; "status",`String "filled";
     "status",`String "rejected"; "status",`String "unknown"];
  let root=Filename.temp_file "btc-state-test" "" in Sys.remove root; Unix.mkdir root 0o700;
  let pending=Filename.concat root "pending" and owned=Filename.concat root "owned" in
  Fun.protect ~finally:(fun () ->
    List.iter (fun path -> if Sys.file_exists path then Sys.remove path) [pending;owned;owned^".tmp"];
    Unix.rmdir root) (fun () ->
    let saved="buy "^id^" 0.001000000" in
    Btc_order_state.write_atomic pending saved;
    let events=ref 0 in
    let run lookup record = Btc_order_state.reconcile ~pending_path:pending ~owned_path:owned ~lookup ~record in
    let record _ _ _ = incr events in
    check "unknown response keeps durable intent" (Result.is_error (run (fun _ -> Error "timeout") record));
    check "wrong result keeps durable intent" (Result.is_error (run (fun _ -> Ok (replace "symbol" (`String "ETHUSD") order)) record));
    check "failure neither clears nor owns" (Btc_order_state.read_line pending=Some saved && not (Sys.file_exists owned) && !events=0);
    (try ignore (run (fun _ -> Ok order) (fun _ _ _ -> failwith "synthetic fsync failure")) with Failure _ -> ());
    check "event failure preserves intent" (Btc_order_state.read_line pending=Some saved && not (Sys.file_exists owned));
    check "pending lifecycle stays pending" (unwrap (run (fun _ -> Ok (replace "status" (`String "partially_filled") order)) record));
    check "pending fill not adopted prematurely" (Sys.file_exists pending && not (Sys.file_exists owned));
    check "partial cancel resolves" (not (unwrap (run (fun _ -> Ok order) record)));
    check "partial ownership is retained" (not (Sys.file_exists pending) && Btc_order_state.read_line owned=Some id);
    let sell_id="jsbotbtcsellSynthetic" in
    let sale=order |> replace "client_order_id" (`String sell_id) |> replace "side" (`String "sell") in
    Btc_order_state.write_atomic pending ("sell "^sell_id^" 0.001000000");
    ignore (unwrap (run (fun _ -> Ok sale) record));
    check "partial canceled sell retains ownership" (Sys.file_exists owned && not (Sys.file_exists pending));
    Btc_order_state.write_atomic pending ("sell "^sell_id^" 0.001000000");
    let full=sale |> replace "status" (`String "filled") |> replace "filled_qty" (`String "0.001000000") in
    ignore (unwrap (run (fun _ -> Ok full) record));
    check "validated full sell clears ownership" (not (Sys.file_exists pending) && not (Sys.file_exists owned));
    check "no pending performs no lookup" (not (unwrap (run (fun _ -> failwith "unexpected lookup") record))));
  print_endline "BTC durable identity, exact quantity and lifecycle checks passed"
