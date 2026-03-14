# Changelog

## Unreleased

### Breaking Changes

* legacy tree/file endpoints are intentionally disabled: `GET /api/tree`, `GET|PUT /api/file` now return `410` and API-first replacements are required (`/api/policies`, `/api/policies/{policy_id}`, `/api/policy-save`)
* web mirror diagnostics endpoint is removed from the API-only surface: `GET /api/validate` now returns `404`
* migration guidance for endpoint replacements is now documented in `README.md` and `docs/OPERATOR_GUIDE_API_ONLY.md`

### Internal Changes

* remove mirror validation diagnostics UI wiring and backend response models from the web app
* expanded Phase 5 hardening tests for packaging completeness, mud API transport error semantics, DB-first save/activation invariants, and deterministic hash/provenance stability

## [0.1.19](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.18...pipeworks-policy-workbench-v0.1.19) (2026-03-14)


### Features

* **ui:** tie activation scope to selected world ([#60](https://github.com/pipe-works/pipeworks-policy-workbench/issues/60)) ([aa7b5f7](https://github.com/pipe-works/pipeworks-policy-workbench/commit/aa7b5f7c5f961604e94e4de38fb477276158faf7))


### Fixes

* **workbench:** hide inactive main tab panels ([ddc3556](https://github.com/pipe-works/pipeworks-policy-workbench/commit/ddc3556d0982d0054fc677003ce19038a7ed467e))
* **workbench:** hide inactive main tab panels ([c8c570d](https://github.com/pipe-works/pipeworks-policy-workbench/commit/c8c570db2ddaaa8dc9bc211b12dd462def737561))

## [0.1.18](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.17...pipeworks-policy-workbench-v0.1.18) (2026-03-14)


### Features

* **workbench:** tab editor and activation scope sections ([a8a2cda](https://github.com/pipe-works/pipeworks-policy-workbench/commit/a8a2cda4560a1cf092d69424c6f76c3b9eb0013b))
* **workbench:** tab editor and activation scope sections ([e8ba7ea](https://github.com/pipe-works/pipeworks-policy-workbench/commit/e8ba7ea1b6c2a09b2872b8e809be1d05f8dc792d))

## [0.1.17](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.16...pipeworks-policy-workbench-v0.1.17) (2026-03-14)


### Fixes

* **web:** remove mirror validation diagnostics from API-only surface ([f5fee11](https://github.com/pipe-works/pipeworks-policy-workbench/commit/f5fee116c85f27eb03a9586bbddc9b89802afd6a))
* **web:** remove mirror validation diagnostics from API-only surface ([56fee18](https://github.com/pipe-works/pipeworks-policy-workbench/commit/56fee1895257bb23b1d0f0b45055a1785f48d07d))

## [0.1.16](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.15...pipeworks-policy-workbench-v0.1.16) (2026-03-14)


### Fixes

* **web:** avoid startup 400s before runtime login ([d4adbfa](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d4adbfa1eace8895add4296e2302e570a4cc8f41))
* **web:** avoid startup 400s before runtime login ([d53ec3c](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d53ec3c349fe63bbc12055659733db19cdffb38d))

## [0.1.15](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.14...pipeworks-policy-workbench-v0.1.15) (2026-03-14)


### Fixes

* **web:** clarify mirror validation authority metadata ([d5c4fee](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d5c4feea4b5e357bd296172f21670d05b1d3bccc))
* **web:** clarify mirror validation authority metadata ([94db9cc](https://github.com/pipe-works/pipeworks-policy-workbench/commit/94db9ccb564d673f01cd463a82d9ee90c3fdfc46))
* **workbench:** harden root portability and package nested ui modules ([#39](https://github.com/pipe-works/pipeworks-policy-workbench/issues/39)) ([4b82f2f](https://github.com/pipe-works/pipeworks-policy-workbench/commit/4b82f2f7985bf291ee4ba58265d4a8c781891655))


### Documentation

* **web:** finalize phase-4 intent comments ([d43b098](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d43b098ddfa58c702431d309f29ffe390af1cf94))
* **web:** finalize phase-4 intent comments ([879bef8](https://github.com/pipe-works/pipeworks-policy-workbench/commit/879bef8f53945a9c4ba1cfc36e40d7074e0efd75))


### Internal Changes

* extract diagnostics and source web services ([67ce60c](https://github.com/pipe-works/pipeworks-policy-workbench/commit/67ce60c4d701ff8e00e2276ff5c72e35344cfc60))
* extract diagnostics and source web services ([841cdfa](https://github.com/pipe-works/pipeworks-policy-workbench/commit/841cdfadf5deb4e658c823545938d1f59accb571))
* fence legacy tree and file endpoints ([6b4c32d](https://github.com/pipe-works/pipeworks-policy-workbench/commit/6b4c32d9590b4daea01449c21371bbd50da29130))
* fence legacy tree and file endpoints ([1aaa667](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1aaa6670263cff2e4b8416d612f1354f4b413c27))
* remove dead service wrappers and unwired tree module ([57200bc](https://github.com/pipe-works/pipeworks-policy-workbench/commit/57200bc06d3908457d47a0f721b6a216f640fe32))
* remove dead service wrappers and unwired tree module ([b46be3f](https://github.com/pipe-works/pipeworks-policy-workbench/commit/b46be3f9db671628820ec688ced36324f0cebc30))
* thin web routes with shared error handling ([168c16b](https://github.com/pipe-works/pipeworks-policy-workbench/commit/168c16b4dafc7dd8880881cd95fb04b5c413b93d))
* thin web routes with shared error handling ([425e8ee](https://github.com/pipe-works/pipeworks-policy-workbench/commit/425e8ee4383cb37896e57275a85736313046dc20))
* **web-services:** centralize mud api transport helpers ([2a7cdfa](https://github.com/pipe-works/pipeworks-policy-workbench/commit/2a7cdfae4023e5457ec11fc0a2a8cf2f83ee1547))
* **web-services:** centralize mud api transport helpers ([b55e208](https://github.com/pipe-works/pipeworks-policy-workbench/commit/b55e20831b0bca173e523ae901dfdeeedb7ab5a4))
* **web-services:** extract policy proxy and local metadata modules ([8fa1a28](https://github.com/pipe-works/pipeworks-policy-workbench/commit/8fa1a28372969620d61658eb1e0e1fcc6933c00b))
* **web-services:** extract policy proxy and local metadata modules ([d0e0ff4](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d0e0ff460a9ba2a2af6b745b61e21fe7514b06a9))
* **web-services:** extract runtime auth option services ([d95a630](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d95a630b76a12e3ea90df857a01a651c5884b461))
* **web-services:** extract runtime auth option services ([7fd215b](https://github.com/pipe-works/pipeworks-policy-workbench/commit/7fd215bc53431f50c2dc6d3cb5448c4853b309b2))
* **web:** improve runtime intent comments and diagnostics guards ([d406448](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d406448ef050cb75d4667153064f22300787bdc3))
* **web:** improve runtime intent comments and diagnostics guards ([dc0b401](https://github.com/pipe-works/pipeworks-policy-workbench/commit/dc0b4010c4fe75c878455e418e158cebe33a8eb9))

## [0.1.14](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.13...pipeworks-policy-workbench-v0.1.14) (2026-03-14)


### Features

* remove offline mode and slim policy tree ([cdfd295](https://github.com/pipe-works/pipeworks-policy-workbench/commit/cdfd295060d64034d9cd4dd9e40c64a1885de085))
* remove offline mode and slim policy tree ([4dc83df](https://github.com/pipe-works/pipeworks-policy-workbench/commit/4dc83df1c29c75fef749945fdeabdbadaea2a8bb))
* **repo:** bootstrap policy workbench scaffold ([2a77d5c](https://github.com/pipe-works/pipeworks-policy-workbench/commit/2a77d5cd4f43dcea183bd2ebe8d9019945b7e213))
* **runtime:** clarify source mode and canonical policy inventory filters ([4c04b6e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/4c04b6e277f07dae9eebc72bf0c6180478b336bd))
* **runtime:** clarify source mode and canonical policy inventory filters ([6234924](https://github.com/pipe-works/pipeworks-policy-workbench/commit/6234924b939fbaa8eb8ebaba91f6780bed7bd47a))
* **sync:** add phase-2 mirror-map planning and safe apply ([1208e82](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1208e82c40162a27cc3f2058e5225115d349f049))
* **sync:** add phase-2 mirror-map planning and safe apply ([29c87b6](https://github.com/pipe-works/pipeworks-policy-workbench/commit/29c87b638c5ffafb217f524f619f6bd7abf22cd5))
* **sync:** add target-only drift contract and step-based sync UX ([93f6c66](https://github.com/pipe-works/pipeworks-policy-workbench/commit/93f6c661201394b4e827a52f2e6b093110b4d3cd))
* **sync:** add target-only drift contract and step-based sync UX ([fcedc76](https://github.com/pipe-works/pipeworks-policy-workbench/commit/fcedc76d6d8443a280c932b1d1448a751b11a81e))
* **web:** add canonical hash alignment status workflow ([1dd958c](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1dd958c80556499672962906915f3f5406a91fcd))
* **web:** add canonical hash alignment status workflow ([1494970](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1494970acf97bac11928b1486b6707fbe5664cb0))
* **web:** add policy editor UI and sync APIs ([e1702fc](https://github.com/pipe-works/pipeworks-policy-workbench/commit/e1702fce3754cf9ac991284de28fe56d99075423))
* **web:** add policy editor UI and sync APIs ([51fae2e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/51fae2e1a1e28adcded4bc8c3297670d58362a19))
* **web:** clarify sync dry-run plan state and feedback ([58d3c68](https://github.com/pipe-works/pipeworks-policy-workbench/commit/58d3c6862e451919cd5858282ab2bdac8e452207))
* **web:** clarify sync dry-run plan state and feedback ([a9e7b8e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/a9e7b8e0980c2fd318dd9f4747fe764589c549a1))
* **web:** improve sync compare modal with side-by-side diff tools ([3ee06bd](https://github.com/pipe-works/pipeworks-policy-workbench/commit/3ee06bd0ad728ccbfa67deb78824f8ed5996f9f7))
* **web:** improve sync compare modal with side-by-side diff tools ([27332b5](https://github.com/pipe-works/pipeworks-policy-workbench/commit/27332b56a585d0576858a3c7420cc5f4c499db5c))
* **workbench:** add activation scope controls for api saves ([#25](https://github.com/pipe-works/pipeworks-policy-workbench/issues/25)) ([b6c7426](https://github.com/pipe-works/pipeworks-policy-workbench/commit/b6c7426bdb45e01b4d6a75ac691cbd021fee84b6))
* **workbench:** add api-first policy inventory and proxy read endpoints ([#23](https://github.com/pipe-works/pipeworks-policy-workbench/issues/23)) ([0f2bebf](https://github.com/pipe-works/pipeworks-policy-workbench/commit/0f2bebf0d21054858ec042e3fa368863b7f64fbb))
* **workbench:** add descriptor-layer and registry authoring support ([d58c777](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d58c7773eb8f18b3d999dfd6c8308171923ed4a1))
* **workbench:** add layer2 selector and registry inference support ([421e5d2](https://github.com/pipe-works/pipeworks-policy-workbench/commit/421e5d220c3fffe7279d6ff4e1eee575a7d24d75))
* **workbench:** align inventory with policy capabilities and db object model ([#36](https://github.com/pipe-works/pipeworks-policy-workbench/issues/36)) ([9203988](https://github.com/pipe-works/pipeworks-policy-workbench/commit/920398805bdb8af3244a388f8b9088c649c1f5b8))
* **workbench:** implement phase-1 scanner validation and serve runtime ([d9bd984](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d9bd984a22479d28522c19e3bb7c788148c70e15))
* **workbench:** implement phase-1 scanner validation and serve runtime ([0f36201](https://github.com/pipe-works/pipeworks-policy-workbench/commit/0f362015850cb567784f7b522e5fb3ff58917692))
* **workbench:** support prompt and tone-profile api authoring ([171d8fc](https://github.com/pipe-works/pipeworks-policy-workbench/commit/171d8fc0b8831665d772c3b63db1c61a844efe9f))
* **workbench:** support prompt and tone-profile API authoring ([1a0a0a6](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1a0a0a6fc8e8fb5a3cb68caebbe72b10dcadafbe))
* **workbench:** switch runtime saves to mud-server policy api ([#19](https://github.com/pipe-works/pipeworks-policy-workbench/issues/19)) ([d6ee4f3](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d6ee4f3800398c35f2a7e833abfd11732c25c174))


### Fixes

* **auth:** enforce admin and superuser server-mode access ([#26](https://github.com/pipe-works/pipeworks-policy-workbench/issues/26)) ([16c0f5e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/16c0f5e45b22375cc16baf0c07a4a80e3adafd3b))
* **ci:** add pytest-cov and disable docs lane ([2b92407](https://github.com/pipe-works/pipeworks-policy-workbench/commit/2b9240708ed28482cced84db9b76b41411e88f70))
* **deps:** bump pipeworks-ipc to v0.1.2 ([0254654](https://github.com/pipe-works/pipeworks-policy-workbench/commit/02546549f2aef812b7a4fcd0ff7592aa43b80158))
* **deps:** bump pipeworks-ipc to v0.1.2 ([9d2646e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/9d2646e2f70c2f5a8dfbab4f6740170bb15e7ec9))
* **runtime:** simplify auth UX and default to offline mode ([661284d](https://github.com/pipe-works/pipeworks-policy-workbench/commit/661284d9c3f54d938cc84c6b8e441cb938908314))
* **runtime:** simplify auth UX and default to offline mode ([22bbe33](https://github.com/pipe-works/pipeworks-policy-workbench/commit/22bbe3370978ed4dbd3724122dea086ff3eacb99))
* **ui:** improve sync impact clarity and hash feedback ([db47497](https://github.com/pipe-works/pipeworks-policy-workbench/commit/db474978ee49bf54d100ec51389f509e824b6b8e))
* **ui:** improve sync impact clarity and hash feedback ([f6d860b](https://github.com/pipe-works/pipeworks-policy-workbench/commit/f6d860ba4ff6ca091bb5483bf1fc66086d29dc85))
* **web:** close hash status coverage gaps ([e73ff36](https://github.com/pipe-works/pipeworks-policy-workbench/commit/e73ff36ec6587555c8d00244f6b4765ec26f6db9))
* **web:** polish phase 3 tree, validation, and sync UX ([ce5cc92](https://github.com/pipe-works/pipeworks-policy-workbench/commit/ce5cc923c127327ca4ffd2b507e9e155acc8cf08))
* **web:** polish phase 3 tree, validation, and sync UX ([a0d635f](https://github.com/pipe-works/pipeworks-policy-workbench/commit/a0d635f888f716dc944ed2f7311a0ceff62aff49))
* **workbench:** enforce api-only authoring surface ([884de92](https://github.com/pipe-works/pipeworks-policy-workbench/commit/884de92888c9de6be3b63943143a96e06f1f3008))
* **workbench:** enforce api-only authoring surface ([541975b](https://github.com/pipe-works/pipeworks-policy-workbench/commit/541975b2010821d4651ed4aadfd49553397846db))


### Internal Changes

* split workbench frontend entry and add DOM contract tests ([857a8e4](https://github.com/pipe-works/pipeworks-policy-workbench/commit/857a8e47c4c3a49c38c7aa171f1dab6b7d60c588))
* split workbench frontend entry and add DOM contract tests ([a0729a9](https://github.com/pipe-works/pipeworks-policy-workbench/commit/a0729a9ed010fdb9b8134780f9b82fb192f03781))
* **workbench:** modularize frontend runtime sync and boot wiring ([cf30373](https://github.com/pipe-works/pipeworks-policy-workbench/commit/cf30373aa4cf0cb23353739f8b60f1d1cbaa3e8b))
* **workbench:** modularize frontend runtime sync and boot wiring ([8d437e6](https://github.com/pipe-works/pipeworks-policy-workbench/commit/8d437e6ebd4ef9895718bd2fd7f4fa7b6e6c3849))

## [0.1.13](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.12...pipeworks-policy-workbench-v0.1.13) (2026-03-14)


### Features

* **workbench:** align inventory with policy capabilities and db object model ([#36](https://github.com/pipe-works/pipeworks-policy-workbench/issues/36)) ([9203988](https://github.com/pipe-works/pipeworks-policy-workbench/commit/920398805bdb8af3244a388f8b9088c649c1f5b8))

## [0.1.12](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.11...pipeworks-policy-workbench-v0.1.12) (2026-03-13)


### Fixes

* **workbench:** enforce api-only authoring surface ([884de92](https://github.com/pipe-works/pipeworks-policy-workbench/commit/884de92888c9de6be3b63943143a96e06f1f3008))
* **workbench:** enforce api-only authoring surface ([541975b](https://github.com/pipe-works/pipeworks-policy-workbench/commit/541975b2010821d4651ed4aadfd49553397846db))

## [0.1.11](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.10...pipeworks-policy-workbench-v0.1.11) (2026-03-13)


### Features

* remove offline mode and slim policy tree ([cdfd295](https://github.com/pipe-works/pipeworks-policy-workbench/commit/cdfd295060d64034d9cd4dd9e40c64a1885de085))
* remove offline mode and slim policy tree ([4dc83df](https://github.com/pipe-works/pipeworks-policy-workbench/commit/4dc83df1c29c75fef749945fdeabdbadaea2a8bb))
* **runtime:** clarify source mode and canonical policy inventory filters ([4c04b6e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/4c04b6e277f07dae9eebc72bf0c6180478b336bd))
* **runtime:** clarify source mode and canonical policy inventory filters ([6234924](https://github.com/pipe-works/pipeworks-policy-workbench/commit/6234924b939fbaa8eb8ebaba91f6780bed7bd47a))


### Fixes

* **runtime:** simplify auth UX and default to offline mode ([661284d](https://github.com/pipe-works/pipeworks-policy-workbench/commit/661284d9c3f54d938cc84c6b8e441cb938908314))
* **runtime:** simplify auth UX and default to offline mode ([22bbe33](https://github.com/pipe-works/pipeworks-policy-workbench/commit/22bbe3370978ed4dbd3724122dea086ff3eacb99))


### Internal Changes

* split workbench frontend entry and add DOM contract tests ([857a8e4](https://github.com/pipe-works/pipeworks-policy-workbench/commit/857a8e47c4c3a49c38c7aa171f1dab6b7d60c588))
* split workbench frontend entry and add DOM contract tests ([a0729a9](https://github.com/pipe-works/pipeworks-policy-workbench/commit/a0729a9ed010fdb9b8134780f9b82fb192f03781))
* **workbench:** modularize frontend runtime sync and boot wiring ([cf30373](https://github.com/pipe-works/pipeworks-policy-workbench/commit/cf30373aa4cf0cb23353739f8b60f1d1cbaa3e8b))
* **workbench:** modularize frontend runtime sync and boot wiring ([8d437e6](https://github.com/pipe-works/pipeworks-policy-workbench/commit/8d437e6ebd4ef9895718bd2fd7f4fa7b6e6c3849))

## [0.1.10](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.9...pipeworks-policy-workbench-v0.1.10) (2026-03-12)


### Fixes

* **auth:** enforce admin and superuser server-mode access ([#26](https://github.com/pipe-works/pipeworks-policy-workbench/issues/26)) ([16c0f5e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/16c0f5e45b22375cc16baf0c07a4a80e3adafd3b))

## [0.1.9](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.8...pipeworks-policy-workbench-v0.1.9) (2026-03-11)


### Features

* **workbench:** add activation scope controls for api saves ([#25](https://github.com/pipe-works/pipeworks-policy-workbench/issues/25)) ([b6c7426](https://github.com/pipe-works/pipeworks-policy-workbench/commit/b6c7426bdb45e01b4d6a75ac691cbd021fee84b6))
* **workbench:** add api-first policy inventory and proxy read endpoints ([#23](https://github.com/pipe-works/pipeworks-policy-workbench/issues/23)) ([0f2bebf](https://github.com/pipe-works/pipeworks-policy-workbench/commit/0f2bebf0d21054858ec042e3fa368863b7f64fbb))

## [0.1.8](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.7...pipeworks-policy-workbench-v0.1.8) (2026-03-11)


### Features

* **workbench:** add descriptor-layer and registry authoring support ([d58c777](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d58c7773eb8f18b3d999dfd6c8308171923ed4a1))
* **workbench:** add layer2 selector and registry inference support ([421e5d2](https://github.com/pipe-works/pipeworks-policy-workbench/commit/421e5d220c3fffe7279d6ff4e1eee575a7d24d75))
* **workbench:** support prompt and tone-profile api authoring ([171d8fc](https://github.com/pipe-works/pipeworks-policy-workbench/commit/171d8fc0b8831665d772c3b63db1c61a844efe9f))
* **workbench:** support prompt and tone-profile API authoring ([1a0a0a6](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1a0a0a6fc8e8fb5a3cb68caebbe72b10dcadafbe))
* **workbench:** switch runtime saves to mud-server policy api ([#19](https://github.com/pipe-works/pipeworks-policy-workbench/issues/19)) ([d6ee4f3](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d6ee4f3800398c35f2a7e833abfd11732c25c174))

## [0.1.7](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.6...pipeworks-policy-workbench-v0.1.7) (2026-03-10)


### Fixes

* **ui:** improve sync impact clarity and hash feedback ([db47497](https://github.com/pipe-works/pipeworks-policy-workbench/commit/db474978ee49bf54d100ec51389f509e824b6b8e))
* **ui:** improve sync impact clarity and hash feedback ([f6d860b](https://github.com/pipe-works/pipeworks-policy-workbench/commit/f6d860ba4ff6ca091bb5483bf1fc66086d29dc85))

## [0.1.6](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.5...pipeworks-policy-workbench-v0.1.6) (2026-03-10)


### Fixes

* **deps:** bump pipeworks-ipc to v0.1.2 ([0254654](https://github.com/pipe-works/pipeworks-policy-workbench/commit/02546549f2aef812b7a4fcd0ff7592aa43b80158))
* **deps:** bump pipeworks-ipc to v0.1.2 ([9d2646e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/9d2646e2f70c2f5a8dfbab4f6740170bb15e7ec9))

## [0.1.5](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.4...pipeworks-policy-workbench-v0.1.5) (2026-03-10)


### Features

* **sync:** add target-only drift contract and step-based sync UX ([93f6c66](https://github.com/pipe-works/pipeworks-policy-workbench/commit/93f6c661201394b4e827a52f2e6b093110b4d3cd))
* **sync:** add target-only drift contract and step-based sync UX ([fcedc76](https://github.com/pipe-works/pipeworks-policy-workbench/commit/fcedc76d6d8443a280c932b1d1448a751b11a81e))
* **web:** add canonical hash alignment status workflow ([1dd958c](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1dd958c80556499672962906915f3f5406a91fcd))
* **web:** add canonical hash alignment status workflow ([1494970](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1494970acf97bac11928b1486b6707fbe5664cb0))
* **web:** clarify sync dry-run plan state and feedback ([58d3c68](https://github.com/pipe-works/pipeworks-policy-workbench/commit/58d3c6862e451919cd5858282ab2bdac8e452207))
* **web:** clarify sync dry-run plan state and feedback ([a9e7b8e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/a9e7b8e0980c2fd318dd9f4747fe764589c549a1))
* **web:** improve sync compare modal with side-by-side diff tools ([3ee06bd](https://github.com/pipe-works/pipeworks-policy-workbench/commit/3ee06bd0ad728ccbfa67deb78824f8ed5996f9f7))
* **web:** improve sync compare modal with side-by-side diff tools ([27332b5](https://github.com/pipe-works/pipeworks-policy-workbench/commit/27332b56a585d0576858a3c7420cc5f4c499db5c))


### Fixes

* **web:** close hash status coverage gaps ([e73ff36](https://github.com/pipe-works/pipeworks-policy-workbench/commit/e73ff36ec6587555c8d00244f6b4765ec26f6db9))

## [0.1.4](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.3...pipeworks-policy-workbench-v0.1.4) (2026-03-10)


### Fixes

* **web:** polish phase 3 tree, validation, and sync UX ([ce5cc92](https://github.com/pipe-works/pipeworks-policy-workbench/commit/ce5cc923c127327ca4ffd2b507e9e155acc8cf08))
* **web:** polish phase 3 tree, validation, and sync UX ([a0d635f](https://github.com/pipe-works/pipeworks-policy-workbench/commit/a0d635f888f716dc944ed2f7311a0ceff62aff49))

## [0.1.3](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.2...pipeworks-policy-workbench-v0.1.3) (2026-03-09)


### Features

* **web:** add policy editor UI and sync APIs ([e1702fc](https://github.com/pipe-works/pipeworks-policy-workbench/commit/e1702fce3754cf9ac991284de28fe56d99075423))
* **web:** add policy editor UI and sync APIs ([51fae2e](https://github.com/pipe-works/pipeworks-policy-workbench/commit/51fae2e1a1e28adcded4bc8c3297670d58362a19))

## [0.1.2](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.1...pipeworks-policy-workbench-v0.1.2) (2026-03-09)


### Features

* **sync:** add phase-2 mirror-map planning and safe apply ([1208e82](https://github.com/pipe-works/pipeworks-policy-workbench/commit/1208e82c40162a27cc3f2058e5225115d349f049))
* **sync:** add phase-2 mirror-map planning and safe apply ([29c87b6](https://github.com/pipe-works/pipeworks-policy-workbench/commit/29c87b638c5ffafb217f524f619f6bd7abf22cd5))

## [0.1.1](https://github.com/pipe-works/pipeworks-policy-workbench/compare/pipeworks-policy-workbench-v0.1.0...pipeworks-policy-workbench-v0.1.1) (2026-03-09)


### Features

* **repo:** bootstrap policy workbench scaffold ([2a77d5c](https://github.com/pipe-works/pipeworks-policy-workbench/commit/2a77d5cd4f43dcea183bd2ebe8d9019945b7e213))
* **workbench:** implement phase-1 scanner validation and serve runtime ([d9bd984](https://github.com/pipe-works/pipeworks-policy-workbench/commit/d9bd984a22479d28522c19e3bb7c788148c70e15))
* **workbench:** implement phase-1 scanner validation and serve runtime ([0f36201](https://github.com/pipe-works/pipeworks-policy-workbench/commit/0f362015850cb567784f7b522e5fb3ff58917692))


### Fixes

* **ci:** add pytest-cov and disable docs lane ([2b92407](https://github.com/pipe-works/pipeworks-policy-workbench/commit/2b9240708ed28482cced84db9b76b41411e88f70))
