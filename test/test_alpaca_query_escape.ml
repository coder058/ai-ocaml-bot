let ()=
  let check input expected=
    let actual=Paper_market.Alpaca_http.query_escape input in
    if actual<>expected then failwith (Printf.sprintf "query_escape %S = %S, expected %S" input actual expected) in
  check "abc-_.~XYZ019" "abc-_.~XYZ019";
  check "a+b/c=" "a%2Bb%2Fc%3D";
  check "a b&c" "a%20b%26c";
  print_endline "query escape checks passed"
