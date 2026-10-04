(** Thin curl-based HTTP helper. Requires [curl] on PATH.
    Dependencies: unix + yojson only (no cohttp). Never prints secrets. *)

type method_ = GET | POST

val request :
  meth:method_ ->
  url:string ->
  headers:(string * string) list ->
  ?body:string ->
  unit ->
  (int * string * string, string) result

val get_json :
  url:string ->
  key_id:string ->
  secret:string ->
  (Yojson.Safe.t, string) result

val get_public_json : url:string -> (Yojson.Safe.t, string) result

val split_status : string -> string * int

val curl_config : (string * string) list -> (string, string) result

val post_json :
  url:string ->
  key_id:string ->
  secret:string ->
  body:string ->
  (Yojson.Safe.t, string) result
