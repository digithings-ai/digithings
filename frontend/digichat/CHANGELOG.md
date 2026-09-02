# Changelog

## [1.4.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.3.2...digichat-v1.4.0) (2026-09-02)


### Features

* **digichat-ui:** zero-radius ink/paper composer chrome ([6291cd3](https://github.com/digithings-ai/digithings/commit/6291cd33d273c1014b913081c7ad960543f51e70))
* **digichat:** inherit utilitarian-terminal v0.1 chrome ([42b93e0](https://github.com/digithings-ai/digithings/commit/42b93e0ebf5081b31d383ccd611f0bdb655a4c93))
* **digiweb:** utilitarian terminal blend — Phase 0 canon promotion ([4641acf](https://github.com/digithings-ai/digithings/commit/4641acfeca6c9f947680b40065b4f774c0df683d))


### Bug Fixes

* close remaining [#2408](https://github.com/digithings-ai/digithings/issues/2408) BYOK low-risk follow-ups ([#3144](https://github.com/digithings-ai/digithings/issues/3144)) ([6b3b922](https://github.com/digithings-ai/digithings/commit/6b3b92272013bcc0ae43f5f4ee89b7c70c25b4fa))
* **digichat:** add byok_model_provider_mismatch to remediable codes ([#3145](https://github.com/digithings-ai/digithings/issues/3145)) ([6c9f708](https://github.com/digithings-ai/digithings/commit/6c9f708a62d736f7be6a0d71df69219f5cd99a13)), closes [#2524](https://github.com/digithings-ai/digithings/issues/2524)
* **digichat:** align embed server theme with referer host ([#2006](https://github.com/digithings-ai/digithings/issues/2006)) ([fb278e9](https://github.com/digithings-ai/digithings/commit/fb278e92b93a0c50a75cbaeb548d9b7497d76c64))
* **digichat:** drop BYOK upstream messages on digigraph_error SSE ([#2536](https://github.com/digithings-ai/digithings/issues/2536)) ([#3132](https://github.com/digithings-ai/digithings/issues/3132)) ([5a1e199](https://github.com/digithings-ai/digithings/commit/5a1e199175c9703eeb2539e86589b3cba0792e56))
* **digichat:** gate forwarded rate-limit IPs ([#3194](https://github.com/digithings-ai/digithings/issues/3194)) ([59319d2](https://github.com/digithings-ai/digithings/commit/59319d2ac8c16bd93af2894b31e862512abc3ca1))
* **digichat:** harden BYOK models route error and rate-limit responses ([5a18f66](https://github.com/digithings-ai/digithings/commit/5a18f66b260d4dcef5ff25aee12cad98c43b7ad1)), closes [#2408](https://github.com/digithings-ai/digithings/issues/2408)
* **digichat:** harden BYOK models route error and rate-limit responses ([#3136](https://github.com/digithings-ai/digithings/issues/3136)) ([4169212](https://github.com/digithings-ai/digithings/commit/41692122dd00d6b5b3a5173c64f8fb67b435aab6)), closes [#2408](https://github.com/digithings-ai/digithings/issues/2408)
* **digichat:** promote reviewed task fixes ([baa7766](https://github.com/digithings-ai/digithings/commit/baa7766d12918ee7906544e20ee63f472c2563a5))
* **digichat:** reopen BYOK panel when key is bound ([#2529](https://github.com/digithings-ai/digithings/issues/2529)) ([9590c54](https://github.com/digithings-ai/digithings/commit/9590c542251f11b9a23cdd9447e01307bb94d648))
* **digichat:** stop stale localStorage from wiping server history ([#3027](https://github.com/digithings-ai/digithings/issues/3027)) ([93eba59](https://github.com/digithings-ai/digithings/commit/93eba5968f6eb65214676950b321a31507698e62))

## [1.3.2](https://github.com/digithings-ai/digithings/compare/digichat-v1.3.1...digichat-v1.3.2) (2026-08-21)


### Bug Fixes

* **byok:** kill a dead auth argument and a refusal that named the wrong model ([#2550](https://github.com/digithings-ai/digithings/issues/2550)) ([337ff56](https://github.com/digithings-ai/digithings/commit/337ff5673194d61748e264826173047dbf880822))
* **byok:** strip the refusal example, and stop a parenthetical crashing startup ([#2568](https://github.com/digithings-ai/digithings/issues/2568)) ([98d7a49](https://github.com/digithings-ai/digithings/commit/98d7a496f8e233e007dd96e7948852bff55d7d60))

## [1.3.1](https://github.com/digithings-ai/digithings/compare/digichat-v1.3.0...digichat-v1.3.1) (2026-08-20)


### Bug Fixes

* **digichat:** tell an embed visitor a BYOK refusal is fixable ([#2525](https://github.com/digithings-ai/digithings/issues/2525)) ([0e23a37](https://github.com/digithings-ai/digithings/commit/0e23a37390940f3a49a4c2108f77875dae59b329))
* **digigraph:** close findings from the independent review of [#2427](https://github.com/digithings-ai/digithings/issues/2427) ([cc5accf](https://github.com/digithings-ai/digithings/commit/cc5accfe688d4d6ea13edd7552f727b11963d16b))
* **digigraph:** correct the "same string" claim and cover the production trace path ([#2537](https://github.com/digithings-ai/digithings/issues/2537)) ([7f4ff15](https://github.com/digithings-ai/digithings/commit/7f4ff15624264a53a57187c3eb0491ba32ef40a3))
* **digigraph:** refuse a bound BYOK key the deployment default would not spend ([#2503](https://github.com/digithings-ai/digithings/issues/2503)) ([dc0fd59](https://github.com/digithings-ai/digithings/commit/dc0fd59ee92acc94c09462d730e72006da77a79d))

## [1.3.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.2.0...digichat-v1.3.0) (2026-08-15)


### Features

* **digichat:** BYOK provider/model catalog + live model list at key step ([#2357](https://github.com/digithings-ai/digithings/issues/2357)) ([330a4a0](https://github.com/digithings-ai/digithings/commit/330a4a0e378779cb88ce4f7fad7e8eb3d18b1f49))


### Bug Fixes

* address remaining CodeRabbit findings from the [#2327](https://github.com/digithings-ai/digithings/issues/2327) re-review ([1d250c7](https://github.com/digithings-ai/digithings/commit/1d250c7257f1f88e9d7f4a365a0cd110b8194c48))
* **digichat:** prefix the BYOK models fetch with the app base path ([#2383](https://github.com/digithings-ai/digithings/issues/2383)) ([535a5a9](https://github.com/digithings-ai/digithings/commit/535a5a9e4fd664e5be3b21366c57ad7de9018992))

## [1.2.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.1.0...digichat-v1.2.0) (2026-08-13)


### Features

* **digichat,digiweb:** bring mermaid/code-block rendering to the primary chat page ([98c41d4](https://github.com/digithings-ai/digithings/commit/98c41d459a3f39b537caa06a60c71302ed85f690))
* **digichat,digiweb:** bring mermaid/code-block rendering to the primary chat page ([f6ecb04](https://github.com/digithings-ai/digithings/commit/f6ecb043dd1acd0bff084d008af209eeab52c305)), closes [#2320](https://github.com/digithings-ai/digithings/issues/2320)
* **digigraph:** make the chat agentic — model-driven retrieval, locate-then-load, enforced tenant scope ([#2295](https://github.com/digithings-ai/digithings/issues/2295)) ([15940d9](https://github.com/digithings-ai/digithings/commit/15940d948857740bbc69fd9bdf71371d6240d87e))
* **digigraph:** promote agentic chat to develop ([155cbcb](https://github.com/digithings-ai/digithings/commit/155cbcbfdf65af14e2e3ac2a91ddb163e19e0dfd))
* **digigraph:** promote agentic chat to develop ([#2302](https://github.com/digithings-ai/digithings/issues/2302)) ([155cbcb](https://github.com/digithings-ai/digithings/commit/155cbcbfdf65af14e2e3ac2a91ddb163e19e0dfd))


### Bug Fixes

* 2 P0 findings from full-UI-suite impeccable critique (invisible button text + free-turn-on-error) ([5e37663](https://github.com/digithings-ai/digithings/commit/5e3766346e867c6a89f582a99f631e3485b18427))
* Controls (/controls) findings from the full-UI-suite critique ([bc838a1](https://github.com/digithings-ai/digithings/commit/bc838a1079b2a70b4f44536efcb42c265624023c))
* **digichat:** assign locked-contact mailto: href client-side ([#2226](https://github.com/digithings-ai/digithings/issues/2226)) ([#2228](https://github.com/digithings-ai/digithings/issues/2228)) ([dd42166](https://github.com/digithings-ai/digithings/commit/dd42166195b855c880be6b1f13ddfc6e05af12b6))
* **digichat:** do not map digivault batch errors as hit counts ([708a870](https://github.com/digithings-ai/digithings/commit/708a870fa9a77c44ed7b04d1966228d29b12d543))
* **digichat:** don't spend a free embed turn on a failed/errored send ([95c6b93](https://github.com/digithings-ai/digithings/commit/95c6b93892acc236c1ccfd07fd6a55fe40c9afe0)), closes [#2246](https://github.com/digithings-ai/digithings/issues/2246)
* **digichat:** mark a truncated activity snippet with an ellipsis ([7617f8a](https://github.com/digithings-ai/digithings/commit/7617f8a09e1f49c3c86fc3100f766e19de443932))
* **digichat:** mark a truncated activity snippet with an ellipsis ([8243245](https://github.com/digithings-ai/digithings/commit/824324585fa1641ee2057f37546c8dea52e58685)), closes [#2316](https://github.com/digithings-ai/digithings/issues/2316)
* **digichat:** split a round's narration from the final answer on round_boundary ([04940a3](https://github.com/digithings-ai/digithings/commit/04940a35388ddaf17f38aaa66ef6597bfd609c68))
* **digichat:** split a round's narration from the final answer on round_boundary ([028a835](https://github.com/digithings-ai/digithings/commit/028a8351e8c6adc5c896159cd2dc7c7785f36b8b))
* **digiweb:** Controls page findings — money-color reuse, dropdown focus loss, unlabeled toggle ([e5d12ce](https://github.com/digithings-ai/digithings/commit/e5d12ce469a1fa2fec6e68688709375abac76583)), closes [#2246](https://github.com/digithings-ai/digithings/issues/2246) [#2248](https://github.com/digithings-ai/digithings/issues/2248)

## [1.1.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.0.0...digichat-v1.1.0) (2026-08-11)


### Features

* **digichat:** add curated language list + browser detection ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([996e2d7](https://github.com/digithings-ai/digithings/commit/996e2d78c48632fcc6de278fba48416a918944f7))
* **digichat:** add LanguageSelect dropdown component ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([7a344c6](https://github.com/digithings-ai/digithings/commit/7a344c692c891bacde2980089dfa3405c0f1bc9c))
* **digichat:** forward response language as X-Digi-Language header ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([cded3ac](https://github.com/digithings-ai/digithings/commit/cded3ac8c27e97b297f4b310ee1ec495ae08519b))
* **digichat:** forward response language to both backend adapters ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([e725130](https://github.com/digithings-ai/digithings/commit/e7251309e0aff10c5a96b3243040ffc791fbd229))
* **digichat:** Foundry adapter prepends response-language directive ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([14d6201](https://github.com/digithings-ai/digithings/commit/14d620157c585b970796b53f68abd703a82de2ce))
* **digichat:** language selector — digigraph + Foundry ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([e7a92c7](https://github.com/digithings-ai/digithings/commit/e7a92c7ddd75f53c49b63662a02f3ad177ee0015))
* **digichat:** render language selector in embed header ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([e54a99b](https://github.com/digithings-ai/digithings/commit/e54a99b128081a03e30fe724720d577ca3b8d491))
* **digichat:** thread showLanguageSelector through tenant config ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([cfe092f](https://github.com/digithings-ai/digithings/commit/cfe092f893c6f6491a0c9fb73b3570f07b8f92bc))


### Bug Fixes

* address CodeRabbit findings for promote [#2053](https://github.com/digithings-ai/digithings/issues/2053) ([#2061](https://github.com/digithings-ai/digithings/issues/2061)) ([d0f4270](https://github.com/digithings-ai/digithings/commit/d0f4270e2a6990205e15cd66cea90756da2d81a9))
* **digichat:** admit embed BYOK ping without DigiChat session ([#2089](https://github.com/digithings-ai/digithings/issues/2089)) ([ef1f41f](https://github.com/digithings-ai/digithings/commit/ef1f41f5b93c6c9cc69156fc4acd880052d4f8e3))
* **digichat:** allow local http parents for embed iframes ([#2096](https://github.com/digithings-ai/digithings/issues/2096)) ([287ab38](https://github.com/digithings-ai/digithings/commit/287ab387b55f6b86389821885eb15f02b007c36a))
* **digichat:** full-height embed, OCC ready origin, parent theme sync ([#2082](https://github.com/digithings-ai/digithings/issues/2082)) ([e1288f2](https://github.com/digithings-ai/digithings/commit/e1288f2bf679b890beb765dc86b290cd4fc22b55))
* **digichat:** read response language at send time, not mount ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([7d6d8ee](https://github.com/digithings-ai/digithings/commit/7d6d8ee8a68ed55a724edf4e1d3e769487201755))
* **digichat:** relax exact react/react-dom pin to fix duplicate install ([cdca505](https://github.com/digithings-ai/digithings/commit/cdca505f5fd056d46b0eda84d2a339c909279d57))
* **digichat:** relax exact react/react-dom pin to fix duplicate install ([a26f8d4](https://github.com/digithings-ai/digithings/commit/a26f8d4c5849fd952a73ea8cf17b0ccd16ef5c6b))
* **digichat:** session-only BYOK via inline terminal flow ([#2086](https://github.com/digithings-ai/digithings/issues/2086)) ([9ece6ee](https://github.com/digithings-ai/digithings/commit/9ece6ee3eac73f4b35c7db97aeda9810f94843cb))
* **digichat:** style and right-align the LanguageSelect trigger ([#2103](https://github.com/digithings-ai/digithings/issues/2103)) ([eab55c1](https://github.com/digithings-ai/digithings/commit/eab55c1b2537a11a4ac384092733ab0763a9e851))
* **digigraph:** preserve multi-turn chat history in workflow prompt ([#2101](https://github.com/digithings-ai/digithings/issues/2101)) ([9849a8f](https://github.com/digithings-ai/digithings/commit/9849a8f28ac397324530c785973c12cf80b2fe6f))
* full-bleed digichat overlay + nav polish for /chat, /chat/occ ([#2185](https://github.com/digithings-ai/digithings/issues/2185)) ([183f2e0](https://github.com/digithings-ai/digithings/commit/183f2e0ff985b0e1a60fab3ed51033a50da5e37d))

## [1.0.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.9.3...digichat-v1.0.0) (2026-08-10)


### Features

* **digichat:** digigraph-centric adapters and digithings.ai cutover ([#2013](https://github.com/digithings-ai/digithings/issues/2013)) ([573b815](https://github.com/digithings-ai/digithings/commit/573b8157dd6a7d1c9ef516ba929266b9816b12d6))
* **digichat:** digithings dogfood completion ([6bd3a9d](https://github.com/digithings-ai/digithings/commit/6bd3a9ddae9c5076259f79cf9dd35d087a208ba3))
* **digichat:** Profile A/B overlays + self-hosted install/deploy docs (Tasks 3–8) ([#2022](https://github.com/digithings-ai/digithings/issues/2022)) ([1993606](https://github.com/digithings-ai/digithings/commit/199360647b0436c0f7debc759983d8a2ec47a563))
* **digichat:** runtime CSP frame-ancestors for stock GHCR ([#2031](https://github.com/digithings-ai/digithings/issues/2031)) ([2c30ee4](https://github.com/digithings-ai/digithings/commit/2c30ee40c30fe95edb23f4d4985d7d19e8329d44))
* **digichat:** simplify embed gate for dogfood slice 1 ([4d05075](https://github.com/digithings-ai/digithings/commit/4d0507548145e13025a66c5d2b0baf737a700430)), closes [#2045](https://github.com/digithings-ai/digithings/issues/2045)
* **digithings:** dogfood cutover — client [#0](https://github.com/digithings-ai/digithings/issues/0) onboard + auth Option A ([#2037](https://github.com/digithings-ai/digithings/issues/2037)) ([df14c20](https://github.com/digithings-ai/digithings/commit/df14c20e256396e1d069f4197ae75ba8660dc95d))
* free-tier digithings LLM + BYOK (digigraph + digichat) ([#2048](https://github.com/digithings-ai/digithings/issues/2048)) ([0f0498e](https://github.com/digithings-ai/digithings/commit/0f0498ea8d14f460078812d816d24083e202d709))
* **occ:** client [#1](https://github.com/digithings-ai/digithings/issues/1) chat at digithings.ai/chat/occ ([209a870](https://github.com/digithings-ai/digithings/commit/209a870ac762777592af4463bb017f14db5fc9b7))
* **occ:** client [#1](https://github.com/digithings-ai/digithings/issues/1) chat demo with corpus routing ([4f7f5c3](https://github.com/digithings-ai/digithings/commit/4f7f5c3726e12ff8687e44d4663c1edf81169385))


### Bug Fixes

* **digichat,digigraph:** prefer-const and ruff format for dogfood CI ([db4b325](https://github.com/digithings-ai/digithings/commit/db4b3253b6fb76db0e83ed75563b1cab3b34fa88))
* **digichat:** embed dogfood contrast and ungated error UX ([6fee5e3](https://github.com/digithings-ai/digithings/commit/6fee5e3b5b77a9167404120cfc17ae7b7fd12b23))
* **digichat:** hide bare graph_update from activity chain ([e419830](https://github.com/digithings-ai/digithings/commit/e4198303d0eb3b5f98ca9b213f183d530c0f0dad))
* **digichat:** opt out of OpenWebUI chrome for dogfood stream ([ea725b2](https://github.com/digithings-ai/digithings/commit/ea725b21761e1f6f99d8b7a954587af2326f0d5e))
* **digichat:** readable Sources rows for dogfood RAG traces ([899b802](https://github.com/digithings-ai/digithings/commit/899b80202555aa4b0cfee3b150eaea48365d7502)), closes [#2045](https://github.com/digithings-ai/digithings/issues/2045)
* **digichat:** remove unused status bar chrome ([7959f4d](https://github.com/digithings-ai/digithings/commit/7959f4d7222ff5e3a774ebec874672ea83daa680))
* **digichat:** restore wordmark header without status bar ([2f4fec8](https://github.com/digithings-ai/digithings/commit/2f4fec8c23658562eedb4fd24d5e9feacb70ed7f))
* **digiquant:** Nautilus image + digichat self-hosted docs follow-up ([#2015](https://github.com/digithings-ai/digithings/issues/2015)) ([bb14aec](https://github.com/digithings-ai/digithings/commit/bb14aec6bce34673879cc91f74858775235a81a7))
* **dogfood:** clean answer prose and force dual-sink retrieval ([c1aa684](https://github.com/digithings-ai/digithings/commit/c1aa6840efcdf4d6488dd05144a1eccb921033a1))

## [0.9.3](https://github.com/digithings-ai/digithings/compare/digichat-v0.9.2...digichat-v0.9.3) (2026-08-08)


### Bug Fixes

* **digichat:** flush FoundryToolLeakFilter's held buffer at stream end ([#2000](https://github.com/digithings-ai/digithings/issues/2000)) ([605d9bd](https://github.com/digithings-ai/digithings/commit/605d9bdde2f855b89e143caaa71c075165a054b8))
* **digichat:** resolve embed tenant theme server-side to kill the load flash ([#2002](https://github.com/digithings-ai/digithings/issues/2002)) ([5284970](https://github.com/digithings-ai/digithings/commit/52849702cc309036581cfeef580cefd59ca3ea22))

## [0.9.2](https://github.com/digithings-ai/digithings/compare/digichat-v0.9.1...digichat-v0.9.2) (2026-08-08)


### Bug Fixes

* **chat:** mermaid diagrams with punctuation in node labels now render instead of falling back to source ([#1996](https://github.com/digithings-ai/digithings/issues/1996))

## [0.9.1](https://github.com/digithings-ai/digithings/compare/digichat-v0.9.0...digichat-v0.9.1) (2026-08-07)


### Features

* **digichat:** map Foundry azure_ai_search activity into the shared digichat chain


### Bug Fixes

* **digichat:** progressive tool stream + bare wait caret; fourth-turn trial form polish ([#1983](https://github.com/digithings-ai/digithings/issues/1983))

## [0.9.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.8.0...digichat-v0.9.0) (2026-08-07)


### Features

* **chat:** ship the house type-out as digichat's waiting state ([c98ceab](https://github.com/digithings-ai/digithings/commit/c98ceab87ea8b6aa5f73550e567de40632908444))
* **chat:** ship the house type-out as digichat's waiting state ([3656503](https://github.com/digithings-ai/digithings/commit/365650323cd92014990d60ac832fc9df8e9b67fa))
* **digichat:** unify the chat UI — canon transcript, mermaid/LaTeX, centred embed ([ead37ba](https://github.com/digithings-ai/digithings/commit/ead37baec4a0063f7c8a77eb8add362bbc73c73e))


### Bug Fixes

* **chat:** repair what the in-session review of [#1971](https://github.com/digithings-ai/digithings/issues/1971) found ([ab54c67](https://github.com/digithings-ai/digithings/commit/ab54c679d9b4a05e2a11a95b04563eeaecd38d4c))
* **design-system:** scope KaTeX to math-rendering apps, and correct what [#1941](https://github.com/digithings-ai/digithings/issues/1941) and [#1940](https://github.com/digithings-ai/digithings/issues/1940) claimed ([#1948](https://github.com/digithings-ai/digithings/issues/1948)) ([286fc87](https://github.com/digithings-ai/digithings/commit/286fc875489e4c62a283b08d956fb6ffd4d793dd))

## [0.8.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.7.0...digichat-v0.8.0) (2026-08-06)


### Features

* **digichat-ui:** render the canon transcript grammar in the embed — tool chain, reasoning, sources
* **digiweb:** render mermaid and LaTeX in the shared chat markdown
* **digichat:** centre the embed transcript instead of running it full-bleed

## [0.7.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.6.0...digichat-v0.7.0) (2026-08-06)


### Features

* **digichat:** accept and store the chat access token from the unlock message
* **digichat:** send the chat access token at request time
* **digichat:** add an optional per-tenant quota gate config
* **digichat:** enforce chat quota server-side when a tenant configures a gate

## [0.6.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.5.0...digichat-v0.6.0) (2026-08-05)


### Features

* **design-system:** retire the QR favicon for a terminal identity ([#1843](https://github.com/digithings-ai/digithings/issues/1843)) ([7966e3b](https://github.com/digithings-ai/digithings/commit/7966e3be1c3ad548bb19835cbb25a769ace1d1e0)), closes [#1841](https://github.com/digithings-ai/digithings/issues/1841)
* **digichat:** add digichat ready/seed postMessage validators ([30094d8](https://github.com/digithings-ai/digithings/commit/30094d8d6372c1326572727b27aaca1bc8ad01a0))
* **digichat:** allow first-party digithings hosts without embed token ([556d9a7](https://github.com/digithings-ai/digithings/commit/556d9a7d4406639791b1bcd229de3e05666eaf66))
* **digichat:** drive embed BYOK/status/layout from tenant flags ([9dfe479](https://github.com/digithings-ai/digithings/commit/9dfe479af361f5f780e2b92ab4366b5f70c519ec))
* **digichat:** parse independent embed UI flags from tenant config ([984c0d6](https://github.com/digithings-ai/digithings/commit/984c0d6c3167161a2adc0f211370b951b825dd87))
* **digichat:** Phase 2 unification — digivault port + digigraph rich mapping ([#1859](https://github.com/digithings-ai/digithings/issues/1859)) ([8f56e17](https://github.com/digithings-ai/digithings/commit/8f56e1783c62d93131472707daef6c61b918412f))
* **digichat:** project embed UI flags through tenant-config API ([e4373f0](https://github.com/digithings-ai/digithings/commit/e4373f031d058f26467fa82970e1c8de871fc199))
* **digichat:** scaffold digithings digichat on Cloudflare Containers ([032493e](https://github.com/digithings-ai/digithings/commit/032493e33b6a22525769319d51724683626b3085))
* **digichat:** shared activity protocol (unification phase 1) ([#1817](https://github.com/digithings-ai/digithings/issues/1817)) ([32f8e92](https://github.com/digithings-ai/digithings/commit/32f8e92626c2ffe905cd5a8bfd8d0806c9ceebbd))
* **digichat:** wire ready/seed protocol into embed session ([2a6c075](https://github.com/digithings-ai/digithings/commit/2a6c0752bcc1a50cf25c7954051e68e63d02cd4e))
* **website:** Phase 3 Pages-native digichat-ui (no Containers) ([eefac60](https://github.com/digithings-ai/digithings/commit/eefac60179db807088335cca1f6177a5183dbb70))
* **website:** retire CF chat Function and native useStackChat stack ([b54c73d](https://github.com/digithings-ai/digithings/commit/b54c73d4487cfd5329d3193801a0f1077f13ec6a))


### Bug Fixes

* **digichat:** accept readonly messages in embed seed ([1767bf3](https://github.com/digithings-ai/digithings/commit/1767bf3e708e7f6642ac2ba4e78a6e64ff962295))
* **digichat:** apply URL hex accent after mount on embed ([#1854](https://github.com/digithings-ai/digithings/issues/1854)) ([720f96c](https://github.com/digithings-ai/digithings/commit/720f96c8f7153a39d6a28637f1c84f62374fa479))
* **digichat:** read embed token/host via useSearchParams ([2763be4](https://github.com/digithings-ai/digithings/commit/2763be4dd41db1a858dd66994d7fbe2e8db64f7f))
* **digichat:** read embed token/host via useSearchParams ([5b167df](https://github.com/digithings-ai/digithings/commit/5b167df1e842e1db98f4d0dc4b910b35ed7e07f3))
* **digichat:** retarget Phase 3 embed to same-origin /embed ([21ee786](https://github.com/digithings-ai/digithings/commit/21ee786b6a34077c867ba9cf8f4e966e69f181ba))
* **digichat:** send trial unlock header at request time ([0daa626](https://github.com/digithings-ai/digithings/commit/0daa626b2e1af2592900643aef0ba1228fc5df39))
* **digichat:** send trial unlock header at request time ([80e2f85](https://github.com/digithings-ai/digithings/commit/80e2f8510bc6f24826ea1abfe1139cfbcb1de4e5))

## [0.5.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.4.1...digichat-v0.5.0) (2026-07-31)


### Features

* **digichat:** add trial_form gate mode and shared turn-limit constants ([4a6706c](https://github.com/digithings-ai/digithings/commit/4a6706c88a79353007b6eb1db7b327e82475eb7a))
* **digichat:** carry chat session id and questions on datatap:gated ([f06cdf9](https://github.com/digithings-ai/digithings/commit/f06cdf97dee8f12a2f0523c0a4adea6315d1166b))
* **digichat:** enforce trial_form gate in /api/chat (402, unlock flag, fail-open) ([fb58be2](https://github.com/digithings-ai/digithings/commit/fb58be21e0bf0de8bfa2448e81e5ff4d0d9a7912))
* **digichat:** in-memory per-IP trial-turn quota ([f86a03a](https://github.com/digithings-ai/digithings/commit/f86a03ae5658bde13e8c51af160ff24f8916b2d8))
* **digichat:** trial_form embed — postMessage gate/unlock handshake + unlock header ([6004410](https://github.com/digithings-ai/digithings/commit/60044101e4839ff239363d654f89aed580dd464e))
* **digichat:** trial_form embed gate mode ([4fcf107](https://github.com/digithings-ai/digithings/commit/4fcf107d8b3d2633c992a6bc7e76e927bab8f41d))


### Bug Fixes

* **digichat:** fall back to the contact card when the parent never answers the gate ([e155c76](https://github.com/digithings-ai/digithings/commit/e155c768e27fe4e6277ac71061a9335b495bc0a2))
* **digichat:** hold the server-side turn cap at the advertised 3 ([bde4bfd](https://github.com/digithings-ai/digithings/commit/bde4bfdac30282e9a65265c49997fc5b74272dec))
* **digichat:** persist the trial unlock and harden the gate's failure modes ([110d74c](https://github.com/digithings-ai/digithings/commit/110d74ca25c93ab4e6bb9d966dd585aefed789be))
* **digichat:** post datatap:gated once per payload, not per stream chunk ([6bb9d72](https://github.com/digithings-ai/digithings/commit/6bb9d72e1626d55b11f946d8914035b7b6c28cdb))

## [0.4.1](https://github.com/digithings-ai/digithings/compare/digichat-v0.4.0...digichat-v0.4.1) (2026-07-19)


### Bug Fixes

* **digichat:** parse azure_ai_search's url_citation annotation shape ([bf5bbe7](https://github.com/digithings-ai/digithings/commit/bf5bbe7fe25634e537d48ad4b4c06c774bd18cea))
* **digichat:** parse azure_ai_search's url_citation annotation shape ([91caa0e](https://github.com/digithings-ai/digithings/commit/91caa0e01c20f457ff37e6a120cfd321c1b62253)), closes [#1601](https://github.com/digithings-ai/digithings/issues/1601)

## [0.4.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.3.0...digichat-v0.4.0) (2026-07-16)


### Features

* **digichat:** add foundry backend, retiring the orphaned relay Function ([c1c10b7](https://github.com/digithings-ai/digithings/commit/c1c10b7bcc26679c758b46fc1381ea399d4b5fae))
* **digichat:** add foundry backend, retiring the orphaned relay Function ([7c9866a](https://github.com/digithings-ai/digithings/commit/7c9866aac9a76dc260ad0d4edc2d5bba351e9960)), closes [#1396](https://github.com/digithings-ai/digithings/issues/1396)

## [0.3.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.2.0...digichat-v0.3.0) (2026-07-12)


### Features

* **design:** canon post-merge batch — deck-at-rest, quiet surfaces, rules-only cleanup, the colophon ([bee93aa](https://github.com/digithings-ai/digithings/commit/bee93aaed6e4e1c2bf0bbb34f2047fc55b16e242))
* **design:** teal ruling + Motion package standardization ([51ac2c8](https://github.com/digithings-ai/digithings/commit/51ac2c8d699613132e38d40618fc423fdd71a32b))
* **design:** the conformance pass — apply the six rulings to the apps ([a2b68ce](https://github.com/digithings-ai/digithings/commit/a2b68cef1a470912d575d4647186c83d9470b062))
* **design:** the design canon, the 28-reference mine, and the ruled conformance pass ([342d452](https://github.com/digithings-ai/digithings/commit/342d452f94e9d70c77a49f7d2441f332ad361a70))
* **digichat,digithings-web:** load chat-core/chat-widgets css ([#1418](https://github.com/digithings-ai/digithings/issues/1418)) ([81d558b](https://github.com/digithings-ai/digithings/commit/81d558baf5e67732649656c9ab6fb67fe22b97c0))
* **digichat:** client-safe embed tenant-config endpoint [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([890533e](https://github.com/digithings-ai/digithings/commit/890533e04b3851961bc63f33cb17b29c15152f56))
* **digichat:** config-driven embed gate/theme/accent/attribution [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([6e5744a](https://github.com/digithings-ai/digithings/commit/6e5744ae3cb8c05a660d27c058fd29a10306ba73))
* **digichat:** derive embed frame-ancestors from the tenant registry [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([b5237c7](https://github.com/digithings-ai/digithings/commit/b5237c78f9bdf815006833f82271e483327e5a48))
* **digichat:** embed markdown rendering, activity box, relay conversation continuity [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([8c4b9dd](https://github.com/digithings-ai/digithings/commit/8c4b9dd54977d452d288827e37a10046123cd91e))
* **digichat:** embed tenant registry from DIGICHAT_EMBED_TENANTS env [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([830f647](https://github.com/digithings-ai/digithings/commit/830f64725b52b3e10cecaf047fce701e0811d71b))
* **digichat:** external-relay SSE stream adapter [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([8b8eea0](https://github.com/digithings-ai/digithings/commit/8b8eea0d1fb99e7163d4b67ad58eaab0cb2e08f8))
* **digichat:** flip theme onto [data-theme] via shared ThemeProvider ([425a941](https://github.com/digithings-ai/digithings/commit/425a941193fdaceeb83f6bcbc2e43a15d060e899))
* **digichat:** pluggable external backends + ungated mode for /embed ([57c7fb3](https://github.com/digithings-ai/digithings/commit/57c7fb3137c0146dc3439576555cb0e18584abb4))
* **digichat:** promote 0.1.1 embed UI release to main ([#1387](https://github.com/digithings-ai/digithings/issues/1387)) ([dda37a9](https://github.com/digithings-ai/digithings/commit/dda37a9b2f7018fb4f89854882d2b84e50e9bc51))
* **digichat:** resolve embed tenants from the registry in /api/chat context [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([08cdefa](https://github.com/digithings-ai/digithings/commit/08cdefa37b4b2796ca0b28f88b0a42fb9b7c6b33))
* **digichat:** reverse the token bridge — shadcn vars derive from canon tokens ([32c8db8](https://github.com/digithings-ai/digithings/commit/32c8db8940a1bebfc88de556ad79673decf4595f))
* **digichat:** route external-relay embed tenants through the relay adapter [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([50d82dc](https://github.com/digithings-ai/digithings/commit/50d82dc0161758aef312cc3c068e5d53561d3445))
* **digichat:** shared embed UI for DataTapStream iframe ([#1384](https://github.com/digithings-ai/digithings/issues/1384)) ([76808eb](https://github.com/digithings-ai/digithings/commit/76808eb32b7aaec3fd27c38bb31d5913ee139f76))
* **digichat:** swap ui/* to thin re-exports of @digithings/web controls ([#1419](https://github.com/digithings-ai/digithings/issues/1419)) ([7079da4](https://github.com/digithings-ai/digithings/commit/7079da49b2ca43886f8577e1c18cdd4f41bad1d3))
* **digichat:** terminal-style embed chat matching digithings.ai/chat idiom [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([f596d0b](https://github.com/digithings-ai/digithings/commit/f596d0b286561777e15a1e9fdf1e97d48e648702))
* **digiweb:** create frontend design-suite module (reference + agent surface + tailwind bridge) ([c8072de](https://github.com/digithings-ai/digithings/commit/c8072ded32fd7b7ae3a5ed9c2ffde0fa5ce6f95c))
* **frontend:** canon ratchet — CI guard, MIGRATION.md, skill update ([a73bafe](https://github.com/digithings-ai/digithings/commit/a73bafe0c896a0866d8713638f6ec901eec22e32))


### Bug Fixes

* **digichat:** §16 conformance — tool chips wear the accent, semantics use tokens ([a15ca84](https://github.com/digithings-ai/digithings/commit/a15ca8467530998f2b0c35b70fe012c72e4325c3))
* **digichat:** BYOK test error rides --down, not digikey's livery (§16) ([0cfa709](https://github.com/digithings-ai/digithings/commit/0cfa7098e9696fd4fbbeb483b5e51eabf3117bf8))
* **digichat:** dedupe relay's terminal full-text re-emit in embed answers ([#1393](https://github.com/digithings-ai/digithings/issues/1393)) ([48b043b](https://github.com/digithings-ai/digithings/commit/48b043bed047aec86c1ed2bc15337eac50db7ff7))
* **digichat:** Dockerfile @digithings/web copy, embed theme override, relay dedup ([#1434](https://github.com/digithings-ai/digithings/issues/1434)) ([6f5f67e](https://github.com/digithings-ai/digithings/commit/6f5f67e02d73a78b419700cb683d73fbbf81cb48))
* **digichat:** Dockerfile @digithings/web copy, embed theme override, relay dedup (Part of [#1434](https://github.com/digithings-ai/digithings/issues/1434)) ([595cc3d](https://github.com/digithings-ai/digithings/commit/595cc3d84144007a5f289f4657bd2425bfca550c))
* **digichat:** drop misleading EMBED_FRAME_ANCESTORS compat export [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([42df93a](https://github.com/digithings-ai/digithings/commit/42df93a84f30aa61e0123a3c26796086c4fb904b))
* **digichat:** embed polish — pinned input, dead copy button, duplicated traces ([#1392](https://github.com/digithings-ai/digithings/issues/1392)) ([8209e26](https://github.com/digithings-ai/digithings/commit/8209e2689c9a0d78a69093a70d7c410e51c6fd95))
* **digichat:** include digichat-ui workspace in Docker build ([#1386](https://github.com/digithings-ai/digithings/issues/1386)) ([b61424a](https://github.com/digithings-ai/digithings/commit/b61424ab7ad97951a3c4aa43d92fb3b92cc9e372))
* **digichat:** make digigraph/digiquant/digismith health checks optional ([94db2a9](https://github.com/digithings-ai/digithings/commit/94db2a95faa46ff5d70e7bf10dfb69a1b6bc97c2))
* **digichat:** make digigraph/digiquant/digismith health checks optional ([6971d32](https://github.com/digithings-ai/digithings/commit/6971d328f199f602d649e87c635640f0bf364200)), closes [#1346](https://github.com/digithings-ai/digithings/issues/1346)
* **digichat:** make embed light theme override the app-level dark class [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([41ffd13](https://github.com/digithings-ai/digithings/commit/41ffd1329dc1392928ec7ca67a470bbbe59455af))
* **digichat:** pass DIGICHAT_EMBED_TENANTS at Docker build time, fix musl native deps ([69d14d4](https://github.com/digithings-ai/digithings/commit/69d14d41b285ee6a86fca0273d943ef28232fdd6))
* **digichat:** pass DIGICHAT_EMBED_TENANTS at Docker build time, fix musl native deps ([343b826](https://github.com/digithings-ai/digithings/commit/343b82687fb1b0f68f093d82c5d2cf348bc6cae8)), closes [#1355](https://github.com/digithings-ai/digithings/issues/1355)
* **digichat:** propagate the rose livery split into the live app theme ([6ac3502](https://github.com/digithings-ai/digithings/commit/6ac3502ff32f766059a4f77148d92fcb8a02a7f5)), closes [#1369](https://github.com/digithings-ai/digithings/issues/1369)
* **digichat:** read embed token/host from URL at send time ([#1339](https://github.com/digithings-ai/digithings/issues/1339)) ([91d1cd9](https://github.com/digithings-ai/digithings/commit/91d1cd9e493dcd78298c888e22672e3fec5b1681))
* **digichat:** require per-tenant token for embed registry resolution ([a7f31cd](https://github.com/digithings-ai/digithings/commit/a7f31cd297dc7d296213839b90b4cc0746e73866))
* **digichat:** split non-secret embed hostnames from DIGICHAT_EMBED_TENANTS at build ([83d1d73](https://github.com/digithings-ai/digithings/commit/83d1d73ca35b843eff5e9d56fce5a0b3830e6b47))
* **digichat:** split non-secret embed hostnames from DIGICHAT_EMBED_TENANTS at build ([9363398](https://github.com/digithings-ai/digithings/commit/9363398b8e124df3157b3aaf2e114ec8e61eb385)), closes [#1360](https://github.com/digithings-ai/digithings/issues/1360)
* **digichat:** stop embed host resolution from claiming its own origin ([41d0c2b](https://github.com/digithings-ai/digithings/commit/41d0c2bf7abc317694a0b5473c6164f30f49f0a4))
* **digichat:** stop embed host resolution from claiming its own origin ([eb10fa1](https://github.com/digithings-ai/digithings/commit/eb10fa1a626644ef308deb163a4058107e096882)), closes [#1372](https://github.com/digithings-ai/digithings/issues/1372)
* **digichat:** treat explicit empty DIGICHAT_ENABLED_SERVICES as zero services ([dcfaa22](https://github.com/digithings-ai/digithings/commit/dcfaa220509af5d5c465e98e4d201875140fa1d5))
* **digichat:** treat explicit empty DIGICHAT_ENABLED_SERVICES as zero services ([0fbacac](https://github.com/digithings-ai/digithings/commit/0fbacac1ca6c6774a3e8df629a5f1657b552cc29))
* **digichat:** type-safe embedConfig narrowing for the relay branch [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([00f4180](https://github.com/digithings-ai/digithings/commit/00f4180b21f33fb01786d723d3c6f6b18ee6bf1e))
* **frontend:** hero/nav clearance, TerminalManifest aria-pressed, digichat dev CSP ([#1434](https://github.com/digithings-ai/digithings/issues/1434)) ([ff93649](https://github.com/digithings-ai/digithings/commit/ff93649495cf0252ea1b71755581765955cf82be))
* **frontend:** hero/nav clearance, TerminalManifest aria-pressed, digichat dev CSP (Part of [#1434](https://github.com/digithings-ai/digithings/issues/1434)) ([b109ad6](https://github.com/digithings-ai/digithings/commit/b109ad63461e6bdc72da0ff9d0e34459d6137ebf))

## [0.2.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.1.0...digichat-v0.2.0) (2026-07-07)


### Features

* **design:** canon post-merge batch — deck-at-rest, quiet surfaces, rules-only cleanup, the colophon ([bee93aa](https://github.com/digithings-ai/digithings/commit/bee93aaed6e4e1c2bf0bbb34f2047fc55b16e242))
* **design:** teal ruling + Motion package standardization ([51ac2c8](https://github.com/digithings-ai/digithings/commit/51ac2c8d699613132e38d40618fc423fdd71a32b))
* **design:** the conformance pass — apply the six rulings to the apps ([a2b68ce](https://github.com/digithings-ai/digithings/commit/a2b68cef1a470912d575d4647186c83d9470b062))
* **design:** the design canon, the 28-reference mine, and the ruled conformance pass ([342d452](https://github.com/digithings-ai/digithings/commit/342d452f94e9d70c77a49f7d2441f332ad361a70))
* **digichat:** client-safe embed tenant-config endpoint [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([890533e](https://github.com/digithings-ai/digithings/commit/890533e04b3851961bc63f33cb17b29c15152f56))
* **digichat:** config-driven embed gate/theme/accent/attribution [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([6e5744a](https://github.com/digithings-ai/digithings/commit/6e5744ae3cb8c05a660d27c058fd29a10306ba73))
* **digichat:** derive embed frame-ancestors from the tenant registry [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([b5237c7](https://github.com/digithings-ai/digithings/commit/b5237c78f9bdf815006833f82271e483327e5a48))
* **digichat:** embed markdown rendering, activity box, relay conversation continuity [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([8c4b9dd](https://github.com/digithings-ai/digithings/commit/8c4b9dd54977d452d288827e37a10046123cd91e))
* **digichat:** embed tenant registry from DIGICHAT_EMBED_TENANTS env [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([830f647](https://github.com/digithings-ai/digithings/commit/830f64725b52b3e10cecaf047fce701e0811d71b))
* **digichat:** external-relay SSE stream adapter [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([8b8eea0](https://github.com/digithings-ai/digithings/commit/8b8eea0d1fb99e7163d4b67ad58eaab0cb2e08f8))
* **digichat:** per-IP rate limiting on the anonymous /embed chat path ([c452f68](https://github.com/digithings-ai/digithings/commit/c452f6803fe345005e8b667ca74f235299a44212))
* **digichat:** per-IP rate limiting on the anonymous /embed chat path ([5707ae9](https://github.com/digithings-ai/digithings/commit/5707ae9f669cb6b86ad3745bfabbfc04ffe61317)), closes [#1251](https://github.com/digithings-ai/digithings/issues/1251)
* **digichat:** pluggable external backends + ungated mode for /embed ([57c7fb3](https://github.com/digithings-ai/digithings/commit/57c7fb3137c0146dc3439576555cb0e18584abb4))
* **digichat:** product-as-hero /welcome marketing route + CodeSampleBand ([#1218](https://github.com/digithings-ai/digithings/issues/1218)) ([50a55e1](https://github.com/digithings-ai/digithings/commit/50a55e155a21782cd598d043f1d2f36d91f24180))
* **digichat:** product-as-hero /welcome marketing route + CodeSampleBand [[#1218](https://github.com/digithings-ai/digithings/issues/1218)] ([fc94366](https://github.com/digithings-ai/digithings/commit/fc9436640108c82b40a4a6d8a6154cdedc77ab66))
* **digichat:** resolve embed tenants from the registry in /api/chat context [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([08cdefa](https://github.com/digithings-ai/digithings/commit/08cdefa37b4b2796ca0b28f88b0a42fb9b7c6b33))
* **digichat:** route external-relay embed tenants through the relay adapter [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([50d82dc](https://github.com/digithings-ai/digithings/commit/50d82dc0161758aef312cc3c068e5d53561d3445))
* **digichat:** shared embed UI for DataTapStream iframe ([#1384](https://github.com/digithings-ai/digithings/issues/1384)) ([76808eb](https://github.com/digithings-ai/digithings/commit/76808eb32b7aaec3fd27c38bb31d5913ee139f76))
* **digichat:** terminal-style embed chat matching digithings.ai/chat idiom [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([f596d0b](https://github.com/digithings-ai/digithings/commit/f596d0b286561777e15a1e9fdf1e97d48e648702))
* **digiquant:** DB calibration sync and tearsheet UX overhaul ([4357523](https://github.com/digithings-ai/digithings/commit/4357523765166ed318a904155b496dd408b0ab3d)), closes [#1067](https://github.com/digithings-ai/digithings/issues/1067)
* **digiquant:** DB calibration sync, tearsheet refresh, and digiquant-web landing polish ([f060458](https://github.com/digithings-ai/digithings/commit/f060458e3c36a0084426de7717d3dfbb62a3d5c1))


### Bug Fixes

* **digichat:** §16 conformance — tool chips wear the accent, semantics use tokens ([a15ca84](https://github.com/digithings-ai/digithings/commit/a15ca8467530998f2b0c35b70fe012c72e4325c3))
* **digichat:** BYOK test error rides --down, not digikey's livery (§16) ([0cfa709](https://github.com/digithings-ai/digithings/commit/0cfa7098e9696fd4fbbeb483b5e51eabf3117bf8))
* **digichat:** dedupe relay's terminal full-text re-emit in embed answers ([#1393](https://github.com/digithings-ai/digithings/issues/1393)) ([48b043b](https://github.com/digithings-ai/digithings/commit/48b043bed047aec86c1ed2bc15337eac50db7ff7))
* **digichat:** drop misleading EMBED_FRAME_ANCESTORS compat export [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([42df93a](https://github.com/digithings-ai/digithings/commit/42df93a84f30aa61e0123a3c26796086c4fb904b))
* **digichat:** embed polish — pinned input, dead copy button, duplicated traces ([#1392](https://github.com/digithings-ai/digithings/issues/1392)) ([8209e26](https://github.com/digithings-ai/digithings/commit/8209e2689c9a0d78a69093a70d7c410e51c6fd95))
* **digichat:** include digichat-ui workspace in Docker build ([#1386](https://github.com/digithings-ai/digithings/issues/1386)) ([b61424a](https://github.com/digithings-ai/digithings/commit/b61424ab7ad97951a3c4aa43d92fb3b92cc9e372))
* **digichat:** make digigraph/digiquant/digismith health checks optional ([94db2a9](https://github.com/digithings-ai/digithings/commit/94db2a95faa46ff5d70e7bf10dfb69a1b6bc97c2))
* **digichat:** make digigraph/digiquant/digismith health checks optional ([6971d32](https://github.com/digithings-ai/digithings/commit/6971d328f199f602d649e87c635640f0bf364200)), closes [#1346](https://github.com/digithings-ai/digithings/issues/1346)
* **digichat:** make embed light theme override the app-level dark class [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([41ffd13](https://github.com/digithings-ai/digithings/commit/41ffd1329dc1392928ec7ca67a470bbbe59455af))
* **digichat:** pass DIGICHAT_EMBED_TENANTS at Docker build time, fix musl native deps ([69d14d4](https://github.com/digithings-ai/digithings/commit/69d14d41b285ee6a86fca0273d943ef28232fdd6))
* **digichat:** pass DIGICHAT_EMBED_TENANTS at Docker build time, fix musl native deps ([343b826](https://github.com/digithings-ai/digithings/commit/343b82687fb1b0f68f093d82c5d2cf348bc6cae8)), closes [#1355](https://github.com/digithings-ai/digithings/issues/1355)
* **digichat:** require per-tenant token for embed registry resolution ([a7f31cd](https://github.com/digithings-ai/digithings/commit/a7f31cd297dc7d296213839b90b4cc0746e73866))
* **digichat:** split non-secret embed hostnames from DIGICHAT_EMBED_TENANTS at build ([83d1d73](https://github.com/digithings-ai/digithings/commit/83d1d73ca35b843eff5e9d56fce5a0b3830e6b47))
* **digichat:** split non-secret embed hostnames from DIGICHAT_EMBED_TENANTS at build ([9363398](https://github.com/digithings-ai/digithings/commit/9363398b8e124df3157b3aaf2e114ec8e61eb385)), closes [#1360](https://github.com/digithings-ai/digithings/issues/1360)
* **digichat:** stop embed host resolution from claiming its own origin ([41d0c2b](https://github.com/digithings-ai/digithings/commit/41d0c2bf7abc317694a0b5473c6164f30f49f0a4))
* **digichat:** stop embed host resolution from claiming its own origin ([eb10fa1](https://github.com/digithings-ai/digithings/commit/eb10fa1a626644ef308deb163a4058107e096882)), closes [#1372](https://github.com/digithings-ai/digithings/issues/1372)
* **digichat:** treat explicit empty DIGICHAT_ENABLED_SERVICES as zero services ([dcfaa22](https://github.com/digithings-ai/digithings/commit/dcfaa220509af5d5c465e98e4d201875140fa1d5))
* **digichat:** treat explicit empty DIGICHAT_ENABLED_SERVICES as zero services ([0fbacac](https://github.com/digithings-ai/digithings/commit/0fbacac1ca6c6774a3e8df629a5f1657b552cc29))
* **digichat:** type-safe embedConfig narrowing for the relay branch [[#1312](https://github.com/digithings-ai/digithings/issues/1312)] ([00f4180](https://github.com/digithings-ai/digithings/commit/00f4180b21f33fb01786d723d3c6f6b18ee6bf1e))


### Reverts

* **frontend:** undo epic [#1200](https://github.com/digithings-ai/digithings/issues/1200) landing redesign per design review [[#1308](https://github.com/digithings-ai/digithings/issues/1308)] ([05a9a9d](https://github.com/digithings-ai/digithings/commit/05a9a9d963699cbe6d6af0574bbb179086dff1db))
* **frontend:** undo epic [#1200](https://github.com/digithings-ai/digithings/issues/1200) landing redesign per design review [[#1308](https://github.com/digithings-ai/digithings/issues/1308)] ([bea43d7](https://github.com/digithings-ai/digithings/commit/bea43d7b1f674a4365597e3adef1e7a688a86554))
