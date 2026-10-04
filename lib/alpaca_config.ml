(* Alpaca paper trading origin only. The process has no live-trading URL. *)

let paper_base_url = "https://paper-api.alpaca.markets"

let validate_base_url url =
  let url =
    let n = String.length url in
    if n > 0 && url.[n - 1] = '/' then String.sub url 0 (n - 1) else url
  in
  if url = paper_base_url then Ok ()
  else Error "trading origin is not the exact Alpaca paper HTTPS origin"

let getenv_first names =
  let rec loop = function
    | [] -> None
    | name :: rest ->
      (match Sys.getenv_opt name with
       | Some value when String.trim value <> "" -> Some value
       | _ -> loop rest)
  in loop names

let api_key_id () = getenv_first [ "APCA_API_KEY_ID"; "ALPACA_API_KEY" ]
let api_secret_key () = getenv_first [ "APCA_API_SECRET_KEY"; "ALPACA_SECRET_KEY" ]
