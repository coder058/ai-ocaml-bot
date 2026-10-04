(* SOURCE: Alpaca crypto order quantities allow nine decimal places. Store
   quantities/prices as integer nanounits; no Float formatting may enlarge a
   broker-reported balance. Out-of-range values fail instead of overflowing. *)
type t = int64
let scale = 1_000_000_000L
let digits = 9
let zero = 0L
let of_string text =
  let pieces = String.split_on_char '.' text in
  let valid s = s <> "" && String.for_all (fun c -> c >= '0' && c <= '9') s in
  match pieces with
  | [whole] | [whole; ""] when valid whole ->
    (try let v=Int64.of_string whole in
      if v > Int64.div Int64.max_int scale then Error "decimal exceeds supported range"
      else Ok (Int64.mul v scale) with _ -> Error "invalid decimal")
  | [whole; fraction] when valid whole && valid fraction ->
    (* SOURCE: truncating excess broker decimal places is conservative for
       positive balances. It never rounds an order above available quantity. *)
    let fraction = if String.length fraction > digits then String.sub fraction 0 digits
      else fraction ^ String.make (digits - String.length fraction) '0' in
    (try let w=Int64.of_string whole and f=Int64.of_string fraction in
      if w > Int64.div (Int64.sub Int64.max_int f) scale then Error "decimal exceeds supported range"
      else Ok (Int64.add (Int64.mul w scale) f) with _ -> Error "invalid decimal")
  | _ -> Error "decimal must be a nonnegative ordinary decimal"
let of_float value =
  if not (Float.is_finite value) || value < 0. then Error "invalid numeric decimal"
  else of_string (Printf.sprintf "%.9f" value)
let to_string value =
  if value < zero then invalid_arg "negative quantity";
  Printf.sprintf "%Ld.%09Ld" (Int64.div value scale) (Int64.rem value scale)
let to_float value = float_of_string (to_string value)
let floor_grid value step =
  if step <= zero then Error "nonpositive increment"
  else Ok (Int64.sub value (Int64.rem value step))
let ceil_grid value step =
  match floor_grid value step with
  | Error _ as error -> error
  | Ok floored when floored = value -> Ok value
  | Ok floored when floored <= Int64.sub Int64.max_int step -> Ok (Int64.add floored step)
  | _ -> Error "rounded value exceeds supported range"
let ratio numerator denominator =
  (* SOURCE: long division produces exactly nine fractional quotient digits,
     rounding down. Bounds protect the Int64 remainder and quotient. *)
  if denominator <= zero then Error "nonpositive divisor"
  else
    let rec extend count quotient remainder =
      if count = 0 then Ok quotient
      else if remainder > Int64.div Int64.max_int 10L ||
              quotient > Int64.div (Int64.sub Int64.max_int 9L) 10L then
        Error "division exceeds supported range"
      else let expanded=Int64.mul remainder 10L in
        extend (count-1) (Int64.add (Int64.mul quotient 10L) (Int64.div expanded denominator))
          (Int64.rem expanded denominator) in
    extend digits (Int64.div numerator denominator) (Int64.rem numerator denominator)
