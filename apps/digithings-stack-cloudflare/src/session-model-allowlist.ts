/**
 * House-upstream model slugs a visitor may pick per session (OCC picker).
 *
 * digigraph binds a requested slug only when it is on
 * `DIGI_SESSION_MODEL_ALLOWLIST` (see `digigraph/src/digigraph/model_config.py`),
 * so this list is the session picker's contract with digigraph. It equals the
 * published picker (`available`) at the catalog's price cap: digigraph is the
 * last hop before a bill, so an over-cap id or the OpenRouter router is never
 * bound even if some host hand-writes it into `available`. Raising a cap means
 * raising this list too. The model names live in `config/`, not in code (the
 * model-name literal guard, #5029).
 */
import deployModels from "../../digichat/config/digichat-deploy-models.json";

/** Comma list, the shape digigraph's `session_model_allowlist()` reads. */
export const SESSION_MODEL_ALLOWLIST_DEFAULT: string = deployModels.sessionAllowlist.join(",");
