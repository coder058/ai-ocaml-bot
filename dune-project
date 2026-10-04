(lang dune 3.0)
(name paper_market)
(generate_opam_files true)
(package
 (name paper_market)
 (synopsis "Auditable OCaml Alpaca paper trading lab")
 (depends
  (ocaml (>= 4.13))
  dune
  yojson))
