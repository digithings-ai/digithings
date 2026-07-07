# Changelog

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
