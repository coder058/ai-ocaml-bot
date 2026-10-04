open Paper_market

(* This executable trades PAPER only. The strategy is an uncalibrated systems
   demonstration. No backtest or paper P&L supports a profitability claim. *)

let state_dir =
  match Sys.getenv_opt "PAPER_STATE_DIR" with
  | Some s when s <> "" -> s
  | _ -> ".paper-state"

let pending_path = Filename.concat state_dir "pending"
let owned_path = Filename.concat state_dir "owned"
let event_path = Filename.concat state_dir "events.jsonl"
(* GUESS: # UNCALIBRATED GUESS — reject hot quotes older than five seconds
   before paper submission; calibrate with observed queue and broker delays. *)
let max_quote_age_ns = 5_000_000_000

let quote_age_ns received_ns =
  int_of_float (Unix.gettimeofday () *. 1_000_000_000.) - received_ns

let read_line path =
  if not (Sys.file_exists path) then None
  else
    let ic = open_in path in
    Fun.protect ~finally:(fun () -> close_in_noerr ic) (fun () -> Some (input_line ic))

let write_atomic path value =
  let temp = path ^ ".tmp" in
  let oc = open_out_bin temp in
  output_string oc (value ^ "\n");
  flush oc;
  Unix.fsync (Unix.descr_of_out_channel oc);
  close_out oc;
  Unix.rename temp path

let remove_if_exists path = if Sys.file_exists path then Sys.remove path

let log fmt =
  Printf.ksprintf (fun s ->
    let tm = Unix.gmtime (Unix.time ()) in
    let timestamp = Printf.sprintf "%04d-%02d-%02dT%02d:%02d:%02dZ"
      (tm.tm_year + 1900) (tm.tm_mon + 1) tm.tm_mday
      tm.tm_hour tm.tm_min tm.tm_sec in
    Printf.printf "%s %s\n%!" timestamp s;
    let row = Yojson.Safe.to_string (`Assoc [
      "at", `String timestamp; "message", `String s ]) in
    (* # SOURCE: append-only, owner-only local event journal; fsync before
       submitting another paper order. *)
    let oc = open_out_gen [ Open_creat; Open_append; Open_wronly ] 0o600 event_path in
    Fun.protect ~finally:(fun () -> close_out_noerr oc) (fun () ->
      output_string oc (row ^ "\n");
      flush oc;
      Unix.fsync (Unix.descr_of_out_channel oc))) fmt
  (* # SOURCE: Unix tm_year counts from 1900; tm_mon starts at zero. *)

let client_id side timestamp =
  let clean = String.to_seq timestamp
    |> Seq.filter (function '0' .. '9' | 'A' .. 'Z' | 'a' .. 'z' -> true | _ -> false)
    |> String.of_seq in
  "jsbotbtc" ^ side ^ clean

let filled_qty j =
  match Paper_broker.float (Paper_broker.member "filled_qty" j) with
  | Some x when Float.is_finite x && x >= 0. -> x
  | _ -> 0.

let reconcile_pending () =
  match read_line pending_path with
  | None -> Ok false
  | Some line ->
    (match String.split_on_char ' ' line with
     | [ side; id ] when side = "buy" || side = "sell" ->
       (match Paper_broker.order_by_client_id id with
        | Error e -> Error ("pending order unresolved: " ^ e)
        | Ok order ->
          (match Paper_broker.order_status order with
           | None -> Error "pending order has no status"
           | Some status ->
             log "reconcile id=%s side=%s status=%s filled_qty=%.9f broker_filled_at=%s"
               id side status (filled_qty order)
               (Option.value (Paper_broker.string (Paper_broker.member "filled_at" order))
                  ~default:"none");
             if List.mem status [ "filled"; "canceled"; "expired"; "rejected" ] then (
               if side = "buy" && filled_qty order > 0. then
                 write_atomic owned_path id;
               if side = "sell" && status = "filled" then
                 remove_if_exists owned_path;
               remove_if_exists pending_path;
               Ok false)
             else Ok true))
     | _ -> Error "pending journal malformed")

let broker_state () =
  match Paper_broker.account (), Paper_broker.positions (),
        Paper_broker.any_open_order (), Paper_broker.price_increment () with
  | Error e, _, _, _ | _, Error e, _, _ | _, _, Error e, _
  | _, _, _, Error e -> Error e
  | Ok (status, blocked, buying_power), Ok position_qty,
    Ok has_open_order, Ok tick ->
    if not (List.mem status [ "ACTIVE"; "PAPER_ONLY" ]) || blocked then
      Error ("paper account not tradable: " ^ status)
    else Ok (buying_power, position_qty, has_open_order, tick)

let try_order ?received_ns (previous : Paper_crypto.quote)
    (current : Paper_crypto.quote) =
  match reconcile_pending () with
  | Error e -> log "HALT %s" e
  | Ok true -> log "HOLD pending order is still open"
  | Ok false ->
    (match broker_state () with
     | Error e -> log "HALT broker state: %s" e
     | Ok (buying_power, position_qty, has_open_order, tick) ->
       let owned = read_line owned_path <> None in
       if position_qty > 0. && not owned then
         log "HALT existing BTC position is not owned by this bot"
       else if position_qty = 0. && owned then
         log "HALT ownership marker present but BTC position is zero"
       else
         let owned_dust = owned && position_qty > 0.
           && Paper_crypto.is_dust ~price:current.ask ~qty:position_qty in
         let decision_qty = if owned_dust then 0. else position_qty in
         let action = Paper_crypto.decide ~previous ~current ~position_qty:decision_qty
             ~has_open_order in
         let side_qty_price =
           match action with
           | Paper_crypto.Hold reason -> log "HOLD %s" reason; None
           | Paper_crypto.Buy ->
             let target = Paper_crypto.order_notional Paper_crypto.Experimental_baseline in
             let limit_price = ceil (current.ask /. tick) *. tick in
             if buying_power < target then
               (log "HOLD non-marginable buying power below paper target %.2f" target; None)
             else Option.map (fun q -> "buy", q,
               limit_price)
                 (Paper_crypto.buy_qty ~ask:limit_price ~notional:target)
           | Paper_crypto.Sell ->
             (* # SOURCE: an exit may exceed the entry budget after a price rise;
                allow a risk-reducing sale of the entire bot-owned position. *)
             if Paper_crypto.is_dust ~price:current.bid ~qty:position_qty then
               (log "HOLD owned BTC position below Alpaca $10 sell minimum"; None)
             else Some ("sell", position_qty,
               floor (current.bid /. tick) *. tick)
         in
         (match side_qty_price with
          | None -> ()
          | Some (side, qty, price) ->
            let notional = qty *. price in
               if side = "buy" &&
                 (position_qty *. current.ask +. notional > Paper_crypto.max_position_notional) then
                 (* # SOURCE: user's $500 maximum paper bet; turnover has no daily cap. *)
                 log "HOLD new buy would exceed user $500 BTC position cap"
               else if (match received_ns with
                 | None -> false
                 | Some received_ns ->
                   let age = quote_age_ns received_ns in
                   age < 0 || age > max_quote_age_ns) then
                 log "HOLD hot quote became stale before paper submission"
               else (
                 let id = client_id side current.timestamp in
                 write_atomic pending_path (side ^ " " ^ id);
                 log "SEND paper %s BTC/USD qty=%.9f limit=%g id=%s" side qty price id;
                 let submitted_ns =
                   int_of_float (Unix.gettimeofday () *. 1_000_000_000.) in
                 let response = Paper_broker.submit_ioc ~side ~qty ~limit_price:price
                     ~client_order_id:id in
                 let responded_ns =
                   int_of_float (Unix.gettimeofday () *. 1_000_000_000.) in
                 (* # SOURCE: one millisecond is one million nanoseconds. *)
                 log "ORDER_TIMING id=%s receive_to_http_ms=%s http_roundtrip_ms=%.3f"
                   id
                   (match received_ns with
                    | None -> "unavailable"
                    | Some received_ns ->
                      Printf.sprintf "%.3f"
                        (float_of_int (submitted_ns - received_ns) /. 1_000_000.))
                   (float_of_int (responded_ns - submitted_ns) /. 1_000_000.);
                 match response with
                 | Error e when String.starts_with ~prefix:"HTTP 422:" e ->
                   (* # SOURCE: HTTP 422 is a definite validation rejection;
                      no order was accepted for this client ID. *)
                   remove_if_exists pending_path;
                   log "REJECTED validation: %s" e
                 | Error e -> log "UNCERTAIN submission: %s; journal retained" e
                 | Ok order ->
                   log "ACK id=%s status=%s" id
                     (Option.value (Paper_broker.order_status order) ~default:"unknown"))))

let shadow_decision (previous : Paper_crypto.quote) (current : Paper_crypto.quote) =
  match broker_state () with
  | Error e -> log "SHADOW unavailable broker_state=%s no_order=true" e
  | Ok (_, position_qty, has_open_order, _) ->
    let owned = read_line owned_path <> None in
    if position_qty > 0. && not owned then
      log "SHADOW blocked existing BTC position is not bot-owned no_order=true"
    else if position_qty = 0. && owned then
      log "SHADOW blocked ownership marker conflicts with broker no_order=true"
    else
      let action = Paper_crypto.decide ~previous ~current ~position_qty
          ~has_open_order in
      let reading = match action with
        | Paper_crypto.Buy -> "hypothetical_buy"
        | Paper_crypto.Sell -> "hypothetical_sell"
        | Paper_crypto.Hold reason -> "hold:" ^ reason in
      (* # SOURCE: monitor mode is read-only; the diagnostic rule is
         uncalibrated and must not be represented as a tradable signal. *)
      log "SHADOW diagnostic=%s quote_time=%s no_order=true uncalibrated=true"
        reading current.timestamp

let run ~trade ~once =
  if not (Sys.file_exists state_dir) then Unix.mkdir state_dir 0o700;
  (* # SOURCE: owner-only directory protects the order journal. *)
  let armed = trade && Sys.getenv_opt "PAPER_ORDERS" = Some "1" in
  log "start mode=%s state=%s" (if armed then "PAPER_ORDER" else "MONITOR") state_dir;
  let rec loop previous =
    let current =
      match Paper_crypto.fetch_quote () with
      | Error e -> log "DATA_ERROR %s" e; None
      | Ok q ->
        log "QUOTE BTC/USD t=%s bid=%g ask=%g spread_bps=%.4f"
          q.timestamp q.bid q.ask (Paper_crypto.spread_bps q);
        Some q
    in
    (match previous, current with
     | Some p, Some q when armed -> try_order p q
     | Some p, Some q -> shadow_decision p q
     | _ -> ());
    if not once then (
      (* # GUESS: 30 seconds keeps the diagnostic loop below typical REST
         polling limits. Measure rate-limit headers and signal stability
         before changing it. # UNCALIBRATED GUESS *)
      Unix.sleep 30;
      loop (match current with Some q -> Some q | None -> previous))
  in
  loop None

let hot_socket_path = "/home/ubuntu/jsbot-paper-state/alpaca-hot.sock"
let hot_lock_path = "/home/ubuntu/jsbot-paper-state/alpaca-hot.lock"
(* GUESS: # UNCALIBRATED GUESS — emit at most one quote journal row per five
   seconds for the public monitor; hot decisions still inspect every quote. *)
let quote_log_interval_seconds = 5.

let json_string name json =
  match Paper_broker.member name json with Some (`String s) -> Some s | _ -> None

let json_int name json =
  match Paper_broker.member name json with Some (`Int n) -> Some n | _ -> None

let option_number = function
  | None -> "warming"
  | Some number -> Printf.sprintf "%.5f" number

let utc_day epoch =
  let tm = Unix.gmtime epoch in
  Printf.sprintf "%04d-%02d-%02d" (tm.tm_year + 1900) (tm.tm_mon + 1)
    tm.tm_mday

let warmup_from_capture () =
  (* SOURCE: private Alpaca market capture; yesterday is included so a restart
     near UTC midnight can seed indicators from earlier closed bars. *)
  let archive_dir = "/home/ubuntu/jsbot-paper-state/market-capture/us" in
  let now = Unix.time () in
  let days = [ utc_day (now -. 86_400.); utc_day now ] in
  let state = ref Technical.empty and last_reading = ref None in
  try
    List.iter (fun day ->
      let path = Filename.concat archive_dir (day ^ ".jsonl") in
      if Sys.file_exists path then (
        let input = open_in path in
        Fun.protect ~finally:(fun () -> close_in_noerr input) (fun () ->
          try while true do
            let line = input_line input in
            let record = Yojson.Safe.from_string line in
            match Paper_broker.member "event" record with
            | Some event when Technical.is_btc_bar_event event ->
              (match Technical.parse_bar event with
               | Error error -> failwith ("archive bar: " ^ error)
               | Ok bar ->
                 (match Technical.update !state bar with
                  | Error error -> failwith ("archive order: " ^ error)
                  | Ok Technical.Duplicate -> ()
                  | Ok (Technical.Applied (next, reading)) ->
                    state := next;
                    last_reading := Some reading))
            | _ -> ()
          done with End_of_file -> ()))) days;
    !state, !last_reading
  with error ->
    log "TECHNICAL_WARMUP_FAILED reason=%s using_live_bars=true"
      (Printexc.to_string error);
    Technical.empty, None

let five_minute_snapshot_path =
  "/home/ubuntu/jsbot-paper-state/five-minute-bars.json"

let load_five_minute_snapshot () =
  let snapshot = Yojson.Safe.from_file five_minute_snapshot_path in
  let expected_source =
    "https://data.alpaca.markets/v1beta3/crypto/us/bars" in
  (* SOURCE: the local snapshot is written by refresh_five_minute_bars.py
     from Alpaca US BTC/USD 5Min bars, with a retrieval timestamp. *)
  if json_string "source" snapshot <> Some expected_source ||
     json_string "symbol" snapshot <> Some "BTC/USD" ||
     json_string "timeframe" snapshot <> Some "5Min" then
    failwith "five-minute snapshot source, symbol, or frame mismatch";
  let retrieved_at = Option.value (json_string "retrievedAt" snapshot)
    ~default:"unknown" in
  let rows = match Paper_broker.member "bars" snapshot with
    | Some (`List rows) -> rows
    | _ -> failwith "five-minute snapshot bars absent" in
  let state = ref Technical.empty and last_reading = ref None in
  List.iter (fun row ->
    let event = match row with
      | `Assoc fields -> `Assoc (("T", `String "b") ::
        ("S", `String "BTC/USD") :: fields)
      | _ -> failwith "five-minute snapshot row is not an object" in
    match Technical.parse_bar event with
    | Error error -> failwith ("five-minute bar: " ^ error)
    | Ok bar ->
      (* SOURCE: a five-minute bar is usable only after its close. *)
      if bar.minute mod 5 <> 0 ||
         bar.minute + 5 > int_of_float (Unix.time ()) / 60 then
        failwith "five-minute bar unaligned or not yet closed";
      (match Technical.update ~step:5 !state bar with
       | Error error -> failwith ("five-minute order: " ^ error)
       | Ok Technical.Duplicate -> ()
       | Ok (Technical.Applied (next, reading)) ->
         state := next;
         last_reading := Some reading)) rows;
  !state, !last_reading, retrieved_at

let run_hot_stream ~trade =
  if not (Sys.file_exists state_dir) then Unix.mkdir state_dir 0o700;
  let armed = trade && Sys.getenv_opt "PAPER_ORDERS" = Some "1" in
  (* SOURCE: the production order path always uses the collector's fixed
     socket. A read-only test can choose an isolated fixture socket. *)
  let socket_path = if armed then hot_socket_path else
    Option.value (Sys.getenv_opt "HOT_SOCKET_PATH") ~default:hot_socket_path in
  let lock_path = if socket_path = hot_socket_path then hot_lock_path
    else socket_path ^ ".lock" in
  let worker_lock_path = Filename.concat state_dir "order-worker.lock" in
  log "start mode=%s feed=alpaca_websocket state=%s"
    (if armed then "PAPER_ORDER" else "MONITOR") state_dir;
  log "SIZING policy=experimental_baseline_v1 buy_usd=%.2f max_btc_exposure_usd=%.2f calibrated_low_high=false"
    (Paper_crypto.order_notional Paper_crypto.Experimental_baseline)
    Paper_crypto.max_position_notional;
  let lock_fd = Unix.openfile lock_path [ Unix.O_CREAT; Unix.O_RDWR ] 0o600 in
  Unix.lockf lock_fd Unix.F_LOCK 0;
  let socket = Unix.socket Unix.PF_UNIX Unix.SOCK_DGRAM 0 in
  let bound = ref false in
  Fun.protect ~finally:(fun () ->
    Unix.close socket;
    if !bound && Sys.file_exists socket_path then Unix.unlink socket_path;
    Unix.lockf lock_fd Unix.F_ULOCK 0;
    Unix.close lock_fd) (fun () ->
    if Sys.file_exists socket_path then Unix.unlink socket_path;
    Unix.bind socket (Unix.ADDR_UNIX socket_path);
    bound := true;
    Unix.chmod socket_path 0o600;
    let buffer = Bytes.create 8192 in
    (* GUESS: # UNCALIBRATED GUESS — 8 KiB holds a compact market quote; any
       truncation must fail JSON parsing and halt this consumer. *)
    let active_session = ref None and last_sequence = ref 0 in
    let previous_quote : (Paper_crypto.quote * int) option ref = ref None in
    let warm_state, warm_reading = warmup_from_capture () in
    let technical = ref warm_state in
    let last_reading : Technical.reading option ref = ref warm_reading in
    log "TECHNICAL_WARMUP contiguous_bars=%d last_bar=%s"
      warm_state.count
      (match warm_state.last with None -> "none" | Some bar -> bar.timestamp);
    let five_mtime = ref 0. in
    let five_reading : Technical.reading option ref = ref None in
    let five_retrieved_at = ref "none" in
    let refresh_five_context () =
      if Sys.file_exists five_minute_snapshot_path then (
        let changed = (Unix.stat five_minute_snapshot_path).st_mtime in
        if changed <> !five_mtime then (
          five_mtime := changed;
          try
            let state, reading, retrieved_at = load_five_minute_snapshot () in
            five_reading := reading;
            five_retrieved_at := retrieved_at;
            let bar_time = match state.last with
              | None -> "none" | Some bar -> bar.timestamp in
            let trend, patterns = match reading with
              | None -> "warming", "none"
              | Some value -> value.trend,
                (if value.patterns = [] then "none" else
                   String.concat "," value.patterns) in
            log "TECHNICAL_5M venue=Alpaca symbol=BTC/USD retrieved_at=%s contiguous_bars=%d last_bar=%s trend=%s patterns=%s probability=unknown order_authority=false"
              retrieved_at state.count bar_time trend patterns
          with error ->
            five_reading := None;
            log "TECHNICAL_5M_UNAVAILABLE reason=%s"
              (Printexc.to_string error))) in
    refresh_five_context ();
    let last_reconcile = ref (Unix.gettimeofday ()) in
    let last_quote_log = ref 0. in
    let worker_pid = ref None in
    let reap_worker () =
      match !worker_pid with
      | None -> ()
      | Some pid ->
        (match Unix.waitpid [ Unix.WNOHANG ] pid with
         | 0, _ -> ()
         | _, status ->
           worker_pid := None;
           let outcome = match status with
             | Unix.WEXITED code -> Printf.sprintf "exit=%d" code
             | Unix.WSIGNALED signal -> Printf.sprintf "signal=%d" signal
             | Unix.WSTOPPED signal -> Printf.sprintf "stopped=%d" signal in
           log "HOT_WORKER_FINISHED pid=%d %s" pid outcome) in
    let spawn_worker label job =
      reap_worker ();
      match !worker_pid with
      | Some pid -> log "HOT_WORKER_BUSY candidate=%s active_pid=%d" label pid
      | None ->
        (match Unix.fork () with
         | 0 ->
           Unix.close socket;
           Unix.close lock_fd;
           let order_fd = Unix.openfile worker_lock_path
             [ Unix.O_CREAT; Unix.O_RDWR ] 0o600 in
           Unix.lockf order_fd Unix.F_LOCK 0;
           (try
              job ();
              Unix.lockf order_fd Unix.F_ULOCK 0;
              Unix.close order_fd;
              exit 0
            with error ->
              prerr_endline ("HOT_WORKER_ERROR " ^ Printexc.to_string error);
              Unix.close order_fd;
              exit 1)
         | pid -> worker_pid := Some pid;
           log "HOT_WORKER_STARTED candidate=%s pid=%d" label pid) in
    while true do
      let length, _ = Unix.recvfrom socket buffer 0 (Bytes.length buffer) [] in
      let record =
        try Yojson.Safe.from_string (Bytes.sub_string buffer 0 length)
        with Yojson.Json_error _ -> failwith "invalid or truncated hot datagram" in
      let session = Option.value (json_string "sessionId" record) ~default:"" in
      let sequence = json_int "hotSequence" record in
      let received_ns = json_int "receivedAtNs" record in
      let event = Paper_broker.member "event" record in
      let kind = Option.bind event (json_string "T") |> Option.value ~default:"" in
      refresh_five_context ();
      (match sequence, received_ns with
       | Some sequence, Some received_ns
         when session <> "" && sequence > 0 && received_ns > 0 ->
         if !active_session <> Some session then (
           active_session := Some session;
           (* The process can attach mid-session; continuity starts with the
              first observed datagram and all later gaps fail closed. *)
           last_sequence := sequence - 1;
           previous_quote := None;
           last_reading := None;
           log "HOT_SESSION session=%s first_sequence=%d reset=true" session sequence);
         if sequence <> !last_sequence + 1 then (
           log "HALT hot feed sequence gap session=%s expected=%d received=%d"
             session (!last_sequence + 1) sequence;
           failwith "hot feed sequence gap");
         last_sequence := sequence;
         if kind = "q" then (
           let age_ns = quote_age_ns received_ns in
           if age_ns < 0 || age_ns > max_quote_age_ns then (
             previous_quote := None;
             log "DATA_STALE hot quote age_ms=%d reset=true" (age_ns / 1_000_000))
           else
             match event with
             | None -> failwith "hot quote event missing"
             | Some event ->
               (match Paper_crypto.parse_quote_event event with
                | Error e -> log "HALT invalid hot quote reason=%s" e; failwith e
                | Ok current ->
                  if Unix.gettimeofday () -. !last_quote_log >= quote_log_interval_seconds then (
                    last_quote_log := Unix.gettimeofday ();
                    log "QUOTE BTC/USD t=%s bid=%g ask=%g spread_bps=%.4f feed=alpaca_websocket"
                      current.timestamp current.bid current.ask
                      (Paper_crypto.spread_bps current));
                  (match !previous_quote with
                   | Some (previous, reference_received_ns)
                     when Paper_crypto.sample_due ~reference_received_ns
                       ~current_received_ns:received_ns ->
                     let cross_evidence = Paper_crypto.quote_cross_evidence
                       ~previous ~current in
                     let candidate = Option.is_some cross_evidence in
                     log "HOT_SAMPLE reference_quote_time=%s quote_time=%s window_ms=%d candidate=%b policy=quote_cross_30s_v1"
                       previous.timestamp current.timestamp
                       ((received_ns - reference_received_ns) / 1_000_000) candidate;
                     if candidate then (
                       let cross_direction, trigger_move_bps = Option.get cross_evidence in
                       let decision_ns = int_of_float (Unix.gettimeofday () *. 1_000_000_000.) in
                       let context_frame, context_time, context_trend,
                           context_retrieved =
                         match !five_reading, !last_reading with
                         | Some reading, _ ->
                           "5Min", reading.bar.timestamp, reading.trend,
                           !five_retrieved_at
                         | None, Some reading ->
                           "1Min", reading.bar.timestamp, reading.trend,
                           "stream"
                         | None, None -> "none", "none", "warming", "none" in
                       log "HOT_DECISION quote_time=%s receive_to_decision_ms=%.3f candidate=true policy=quote_cross_30s_v1 reference_bid=%.10g reference_ask=%.10g current_bid=%.10g current_ask=%.10g cross_direction=%s trigger_move_bps=%.8f context_frame=%s context_bar=%s trend=%s context_retrieved=%s probability=unknown"
                         current.timestamp
                         (float_of_int (decision_ns - received_ns) /. 1_000_000.)
                         previous.bid previous.ask current.bid current.ask
                         cross_direction trigger_move_bps
                         context_frame context_time context_trend context_retrieved;
                       spawn_worker "quote_cross" (fun () ->
                         let age_ns = quote_age_ns received_ns in
                         if age_ns < 0 || age_ns > max_quote_age_ns then
                           log "HOLD stale hot quote before broker work age_ms=%d"
                             (age_ns / 1_000_000)
                         else if armed then try_order ~received_ns previous current
                         else shadow_decision previous current));
                     previous_quote := Some (current, received_ns)
                   | Some _ -> ()
                   | None ->
                     previous_quote := Some (current, received_ns);
                     log "HOT_BASELINE quote_time=%s" current.timestamp)))
         else if kind = "b" then
           (match event with
            | None -> failwith "closed bar event missing"
            | Some event ->
              (match Technical.parse_bar event with
               | Error error -> log "HALT invalid closed bar reason=%s" error; failwith error
               | Ok bar ->
                 (match Technical.update !technical bar with
                  | Error error -> log "HALT closed bar sequence reason=%s" error; failwith error
                  | Ok Technical.Duplicate ->
                    log "BAR_DUPLICATE t=%s ignored=true" bar.timestamp
                  | Ok (Technical.Applied (next, reading)) ->
                    technical := next;
                    last_reading := Some reading;
                    log "TECHNICAL venue=Alpaca symbol=BTC/USD bar=%s count=%d gap_reset=%b trend=%s ema20=%s ema50=%s rsi14=%s macd=%s macd_signal=%s patterns=%s probability=unknown order_authority=false"
                      bar.timestamp reading.count reading.gap_reset reading.trend
                      (option_number reading.ema_fast)
                      (option_number reading.ema_slow)
                      (option_number reading.rsi)
                      (option_number reading.macd)
                      (option_number reading.macd_signal)
                      (if reading.patterns = [] then "none" else
                         String.concat "," reading.patterns))))
         else if kind = "u" then
           (match event with
            | Some event ->
              log "BAR_REVISION t=%s ignored_for_decision=true"
                (Option.value (json_string "t" event) ~default:"unknown")
            | None -> failwith "updated bar event missing")
         else
           (log "HALT unexpected hot event type=%s" kind;
            failwith "unexpected hot event type");
         if Unix.gettimeofday () -. !last_reconcile >= 30. then (
           last_reconcile := Unix.gettimeofday ();
           if read_line pending_path <> None then
             spawn_worker "reconcile" (fun () ->
               match reconcile_pending () with
               | Ok _ -> ()
               | Error e -> log "HALT pending reconciliation: %s" e))
       | _ -> failwith "hot datagram missing session, sequence, or receipt time")
    done)

let research_once () =
  List.iter (fun symbol ->
    match Pattern_forge.fetch symbol with
    | Error e -> Printf.printf "PATTERN_FORGE_ERROR symbol=%s reason=%s\n" symbol e
    | Ok frames ->
      List.iter (fun (timeframe, result) ->
        match result with
        | Error e ->
          Printf.printf "PATTERN_FORGE_UNAVAILABLE symbol=%s frame=%s reason=%s\n"
            symbol timeframe e
        | Ok (reading : Pattern_forge.reading) ->
          Printf.printf "PATTERN_FORGE symbol=%s venue=Hyperliquid frame=%s close_time_ms=%d close=%g prior_close=%g return_pct=%+.5f read_only=true\n"
            reading.symbol reading.timeframe reading.close_time_ms
            reading.close reading.prior_close reading.return_pct) frames)
    [ "BTC"; "ETH"; "SOL" ]

let () =
  let trade = ref false and once = ref false and check_broker = ref false in
  let hot_stream = ref false in
  let check_positions = ref false in
  let research = ref false in
  let check_order = ref None in
  Arg.parse [
    "--paper", Arg.Set trade, "Allow paper orders only with PAPER_ORDERS=1";
    "--once", Arg.Set once, "Fetch one live quote and exit";
    "--hot-stream", Arg.Set hot_stream, "Consume the local Alpaca WebSocket datagram feed";
    "--check-broker", Arg.Set check_broker, "Read paper account, orders, position and asset";
    "--check-positions", Arg.Set check_positions, "Read paper positions without trading";
    "--research-once", Arg.Set research, "Read Pattern Forge closed-candle context without trading";
    "--check-order", Arg.String (fun id -> check_order := Some id),
      "Read one paper order by client ID and exit";
  ] (fun _ -> ()) "paper_crypto_main [--paper] [--once|--research-once|--check-broker|--check-positions|--check-order ID]";
  if !research then research_once ()
  else if !check_order <> None then
    match !check_order with
    | None -> assert false
    | Some id ->
      (match Paper_broker.order_by_client_id id with
       | Error e -> prerr_endline ("ORDER_CHECK_FAILED " ^ e); exit 1
       | Ok order ->
         Printf.printf "ORDER_CHECK_OK id=%s symbol=%s side=%s status=%s filled_qty=%.9f\n"
           id
           (Option.value (Paper_broker.string (Paper_broker.member "symbol" order)) ~default:"unknown")
           (Option.value (Paper_broker.string (Paper_broker.member "side" order)) ~default:"unknown")
           (Option.value (Paper_broker.order_status order) ~default:"unknown")
           (filled_qty order))
  else if !check_positions then
    (match Paper_broker.get "/v2/positions" with
     | Error e -> prerr_endline ("POSITIONS_CHECK_FAILED " ^ e); exit 1
     | Ok (`List positions) ->
       List.iter (fun p ->
         let field name =
           Option.value (Paper_broker.string (Paper_broker.member name p))
             ~default:"unknown" in
         Printf.printf "POSITION symbol=%s qty=%s side=%s avg_entry_price=%s\n"
           (field "symbol") (field "qty") (field "side")
           (field "avg_entry_price")) positions
     | Ok _ -> prerr_endline "POSITIONS_CHECK_FAILED unexpected response"; exit 1)
  else if !check_broker then
    match broker_state () with
    | Error e -> prerr_endline ("BROKER_CHECK_FAILED " ^ e); exit 1
    | Ok (buying_power, qty, open_order, tick) ->
      Printf.printf "BROKER_CHECK_OK paper buying_power=%.2f btc_qty=%.9f open_orders=%b price_increment=%g\n"
        buying_power qty open_order tick
  else if !hot_stream then run_hot_stream ~trade:!trade
  else run ~trade:!trade ~once:!once
