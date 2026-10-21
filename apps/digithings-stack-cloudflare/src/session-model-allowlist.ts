/**
 * House-upstream model slugs a visitor may pick per session (OCC picker).
 *
 * digigraph binds a requested slug only when it is on
 * `DIGI_SESSION_MODEL_ALLOWLIST` (see `digigraph/src/digigraph/model_config.py`),
 * so this list is the session picker's contract with digigraph. The published
 * picker (`available`) is a subset: the session list also carries over-cap
 * catalog ids and the OpenRouter router so a deployment that raises the cap
 * can still bind them.
 *
 * The published `available` list is the default price cap. A deployment may
 * raise that cap, and the OpenRouter router is bindable only when configured,
 * so digigraph's allowlist is the wider `sessionAllowlist` (every routable
 * catalog id plus the router). The model names live in `config/`, not in
 * code (the model-name literal guard, #5029).
 */
import deployModels from "../../digichat/config/digichat-deploy-models.json";

/** Comma list, the shape digigraph's `session_model_allowlist()` reads. */
export const SESSION_MODEL_ALLOWLIST_DEFAULT: string = deployModels.sessionAllowlist.join(",");
