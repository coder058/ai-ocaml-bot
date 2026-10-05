(* SOURCE: Alpaca order identity/lifecycle fields:
   https://docs.alpaca.markets/us/docs/orders-at-alpaca .
   Validate durable BTC intent before any ownership/pending mutation. *)
type pending = { side : string; id : string; quantity : Exact_decimal.t option }
type outcome = { status : string; filled : Exact_decimal.t; terminal : bool }

let quantity text =
  (* SOURCE: this adapter submits nine-decimal crypto quantities. Additional
     nonzero digits cannot be truncated when checking a fill bound. *)
  match String.split_on_char '.' text with
  | [_; fraction] when String.length fraction > Exact_decimal.digits &&
      not (String.for_all ((=) '0') (String.sub fraction Exact_decimal.digits
        (String.length fraction - Exact_decimal.digits))) -> Error "unsupported quantity precision"
  | _ -> Exact_decimal.of_string text

let parse_pending line =
  let make side id amount =
    if not (List.mem side ["buy"; "sell"]) ||
       not (String.starts_with ~prefix:("jsbotbtc" ^ side) id) then
      Error "pending BTC identity malformed"
    else Ok {side; id; quantity=amount} in
  match String.split_on_char ' ' line with
  | [side; id] -> make side id None (* SOURCE: legacy durable format. *)
  | [side; id; text] ->
    (match quantity text with
     | Ok amount when amount > Exact_decimal.zero -> make side id (Some amount)
     | _ -> Error "pending BTC quantity malformed")
  | _ -> Error "pending BTC journal malformed"

let validate pending order =
  let field key = Paper_broker.member key order in
  let text key = Paper_broker.string (field key) in
  let decimal key = match text key with
    | Some value -> quantity value | None -> Error "broker quantity missing" in
  (* SOURCE: documented order statuses. Nonterminal/unknown responses never
     clear durable intent. IOC terminal subset is inherited from this engine. *)
  let statuses = ["new"; "partially_filled"; "filled"; "done_for_day";
    "canceled"; "expired"; "replaced"; "pending_cancel"; "pending_replace";
    "accepted"; "pending_new"; "accepted_for_bidding"; "stopped"; "rejected";
    "suspended"; "calculated"; "held"] in
  match text "client_order_id", text "symbol", text "side", text "status",
        decimal "qty", decimal "filled_qty" with
  | Some id, Some ("BTCUSD" | "BTC/USD"), Some side, Some status, Ok amount, Ok filled
    when id=pending.id && side=pending.side && List.mem status statuses &&
      amount > Exact_decimal.zero && filled <= amount &&
      (match pending.quantity with None -> true | Some requested -> amount=requested) &&
      (status<>"filled" || filled=amount) &&
      (status<>"rejected" || filled=Exact_decimal.zero) ->
      Ok {status; filled; terminal=List.mem status ["filled"; "canceled"; "expired"; "rejected"]}
  | _ -> Error "pending BTC broker identity, quantity or lifecycle mismatch"

let read_line path =
  if not (Sys.file_exists path) then None else
  let input=open_in path in
  Fun.protect ~finally:(fun () -> close_in_noerr input) (fun () -> Some (input_line input))

let write_atomic path value =
  let temporary=path ^ ".tmp" in
  let output=open_out_gen [Open_creat; Open_trunc; Open_wronly; Open_binary] 0o600 temporary in
  Fun.protect ~finally:(fun () -> close_out_noerr output) (fun () ->
    output_string output (value ^ "\n"); flush output; Unix.fsync (Unix.descr_of_out_channel output));
  Unix.rename temporary path

let remove path = if Sys.file_exists path then Sys.remove path

let reconcile ~pending_path ~owned_path ~lookup ~record =
  match read_line pending_path with
  | None -> Ok false
  | Some line ->
    (match parse_pending line with
     | Error _ as error -> error
     | Ok pending ->
       match lookup pending.id with
       | Error error -> Error ("pending order unresolved: " ^ error)
       | Ok order ->
         match validate pending order with
         | Error _ as error -> error
         | Ok outcome ->
           (* The event must persist before ownership/pending mutation. *)
           record pending outcome order;
           if not outcome.terminal then Ok true else (
             if pending.side="buy" && outcome.filled > Exact_decimal.zero then
               write_atomic owned_path pending.id;
             if pending.side="sell" && outcome.status="filled" then remove owned_path;
             remove pending_path; Ok false))
