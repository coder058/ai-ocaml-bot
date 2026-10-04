open Paper_market
let unwrap = function Ok value -> value | Error message -> failwith message
let check message condition = if not condition then failwith message
let () =
  (* SOURCE: actual failed BONK/PEPE balance texts from the 4 October audit. *)
  check "BONK balance must not grow" (Exact_decimal.to_string
    (unwrap (Exact_decimal.of_string "26529255.31914894")) = "26529255.319148940");
  check "PEPE balance truncates conservatively" (Exact_decimal.to_string
    (unwrap (Exact_decimal.of_string "22466216.216216221")) = "22466216.216216221");
  (* SOURCE: synthetic grid/long-division fixtures, not market observations. *)
  let value=unwrap (Exact_decimal.of_string "0.399") in
  check "nanounit exactness" (Exact_decimal.to_string value="0.399000000");
  let step=unwrap (Exact_decimal.of_string "0.01") in
  check "floor grid" (Exact_decimal.to_string (unwrap (Exact_decimal.floor_grid value step))="0.390000000");
  check "ceil grid" (Exact_decimal.to_string (unwrap (Exact_decimal.ceil_grid value step))="0.400000000");
  let budget=unwrap (Exact_decimal.of_string "100") in
  let price=unwrap (Exact_decimal.of_string "3") in
  check "long division rounds down" (Exact_decimal.to_string (unwrap (Exact_decimal.ratio budget price))="33.333333333");
  check "negative rejected" (Result.is_error (Exact_decimal.of_string "-1"));
  check "overflow rejected" (Result.is_error (Exact_decimal.of_string "99999999999999999999"));
  print_endline "exact decimal quantity checks passed"
