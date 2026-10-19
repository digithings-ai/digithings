/**
 * House-upstream model slugs a visitor may pick per session (OCC picker).
 *
 * digigraph binds a requested slug only when it is on
 * `DIGI_SESSION_MODEL_ALLOWLIST` (see `digigraph/src/digigraph/model_config.py`),
 * so this list is the session picker's contract: every model the deployment
 * publishes (`apps/digichat/config/digichat-deploy-models.json`) must be
 * listed here, and every slug listed here must be published.
 *
 * The two lists drifted: the published table offered 12 models while the
 * allowlist carried 6, of which only 4 were published. A visitor picking one
 * of the other 8 was silently served the house default instead, and 2
 * allowlisted slugs could never be picked at all.
 *
 * So the default is DERIVED from the published table rather than written out
 * again: the model names live in `config/`, not in code (the model-name
 * literal guard, #5029), and a second copy of the list is the very drift
 * this fixes. `session-model-allowlist.test.js` pins the shape of the
 * derived value and the default model's presence in it.
 */
import deployModels from "../../digichat/config/digichat-deploy-models.json";

/** Comma list, the shape digigraph's `session_model_allowlist()` reads. */
export const SESSION_MODEL_ALLOWLIST_DEFAULT: string = deployModels.available.join(",");
