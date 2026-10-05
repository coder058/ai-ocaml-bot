(* SOURCE: Alpaca UTC quote timestamps have up to nine fractional digits.
   The inherited five-second execution guard applies to both source and
   reception clocks. Exact nanoseconds avoid rounding a future source time. *)
let ns_per_second=1_000_000_000L
let ns_per_minute=60_000_000_000L
let source_ns timestamp =
  try
    let length=String.length timestamp in
    let digits text = text<>"" && String.for_all (fun c -> c>='0' && c<='9') text in
    if length<20 || timestamp.[length-1]<>'Z' || timestamp.[16]<>':' ||
       not (List.for_all (fun (start,size) -> digits (String.sub timestamp start size))
         [0,4;5,2;8,2;11,2;14,2;17,2]) then Error "invalid UTC quote timestamp" else
    let seconds=int_of_string (String.sub timestamp 17 2) in
    let fraction = if length=20 then Some "" else
      if timestamp.[19]<>'.' || length>30 then None else
      let value=String.sub timestamp 20 (length-21) in
      if digits value then Some value else None in
    match Technical.parse_utc_minute (String.sub timestamp 0 16 ^ ":00Z"),fraction with
    | Some minute,Some fraction when seconds<60 && minute>=0 &&
        Int64.of_int minute <= Int64.div (Int64.sub Int64.max_int ns_per_minute) ns_per_minute ->
      let fraction=if fraction="" then 0L else Int64.of_string (fraction ^ String.make (9-String.length fraction) '0') in
      Ok (Int64.add (Int64.mul (Int64.of_int minute) ns_per_minute)
          (Int64.add (Int64.mul (Int64.of_int seconds) ns_per_second) fraction))
    | _ -> Error "invalid UTC quote calendar or precision"
  with _ -> Error "invalid UTC quote timestamp"

let validate ~now_ns ~max_age_ns ~received_ns ~timestamp =
  if now_ns<0L || max_age_ns<0L then Error "invalid freshness clock" else
  match source_ns timestamp with
  | Error _ as error -> error
  | Ok source ->
    let source_age=Int64.sub now_ns source in
    let received_age=Option.map (fun receipt -> Int64.sub now_ns receipt) received_ns in
    if source_age<0L || source_age>max_age_ns ||
       (match received_age with Some age -> age<0L || age>max_age_ns | None -> false) ||
       (match received_ns with Some receipt -> source>receipt | None -> false) then
      Error "quote source or receipt is future/stale"
    else Ok (source_age,received_age)
