# CHANGELOG


## v2.0.0 (2026-06-29)


## v1.0.0 (2026-06-25)


## v1.0.0-rc.5 (2026-06-29)

### Bug Fixes

- Authentikate update
  ([`efaeee9`](https://github.com/arkitektio/mikro-server-next/commit/efaeee92055ea138310a4405a721b42aaced996e))


## v1.0.0-rc.4 (2026-06-26)

### Features

- Removal of stale migrations
  ([`17a8dc3`](https://github.com/arkitektio/mikro-server-next/commit/17a8dc3ce2bc8384f02de13a7830cb92048b175d))


## v1.0.0-rc.3 (2026-06-26)

### Features

- With white noise and optimized Dockerfile
  ([`736c2e6`](https://github.com/arkitektio/mikro-server-next/commit/736c2e6136a10430c61d9efce21d62b26436e950))


## v1.0.0-rc.2 (2026-06-26)

### Bug Fixes

- With CONFIG.md
  ([`a29e94d`](https://github.com/arkitektio/mikro-server-next/commit/a29e94d136898a75b0f0b3938fbd91226b3c5c9b))


## v1.0.0-rc.1 (2026-06-25)

### Bug Fixes

- Add datalayer attributes
  ([`1b83741`](https://github.com/arkitektio/mikro-server-next/commit/1b837417cb61947cb464beea1678f30a18a361c1))

- Add filter type
  ([`2b2503d`](https://github.com/arkitektio/mikro-server-next/commit/2b2503d4968f64b97fbb54766a20742833d13558))

- Add lightpath_view
  ([`b5182d5`](https://github.com/arkitektio/mikro-server-next/commit/b5182d5639247b9247ab2c2efae95bd4cad9eb27))

- Add more
  ([`e9d91cd`](https://github.com/arkitektio/mikro-server-next/commit/e9d91cd87a9305df66e36f80974a7d23bfb7ff99))

- Add organization
  ([`f2f9ec1`](https://github.com/arkitektio/mikro-server-next/commit/f2f9ec16446cf336c6d7536601c4b3a81ca8bddd))

- Add upload grant
  ([`d1faee5`](https://github.com/arkitektio/mikro-server-next/commit/d1faee58165449de5e34a8585cf896e9210a577b))

- Base_color issue
  ([`652bcf3`](https://github.com/arkitektio/mikro-server-next/commit/652bcf3d59f4abf047b5e7e2e157bf2fd85f4e5c))

- Clean all pyflakes-level issues and gate them in CI
  ([`d3a9a59`](https://github.com/arkitektio/mikro-server-next/commit/d3a9a59971d330d560785860412556ac890ad19b))

- delete core/mutations/anchor.py: dead near-duplicate of view.py that was never imported and
  referenced an undefined ViewInput - fix real bugs surfaced by the sweep: missing datetime import
  in queries/rows.py, info not threaded into _create_instance_mask_view_from_partial, duplicated
  ValueHistogramInput/Model defs, dead first Slice class and shadowed Image.views field in types.py
  (SDL verified unchanged) - drop unused assignments while keeping side-effecting calls; remove the
  stale __all__ in core/mutations/__init__.py (listed mutations that no longer exist) - ruff: move
  config to [tool.ruff.lint], ignore F401/F403/F405 in package __init__ re-export files; autofix
  unused imports repo-wide - CI: new lint job gating ruff F,E9 (ANN/D1 stay local-only for now; mypy
  1.15 crashes on django-stubs and is not gated yet)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Config hardening and repo hygiene
  ([`4828cf7`](https://github.com/arkitektio/mikro-server-next/commit/4828cf7648352582fd8849089523995c6071c4df))

- settings.py: DEBUG and ALLOWED_HOSTS now come from config.yaml (django.debug already existed there
  but was ignored); refuse to start with the 'changeme' secret key when debug is false - delete
  tmanage.py (only difference from manage.py was the settings module; pytest sets it via pyproject)
  - replace remaining print() debugging with module loggers (types, adataset, datalayer) and drop
  the bare print(id) lines in schema.py - drop deprecated aioredis dependency (nothing imports it;
  channels-redis ships its own client) - move demo_*.py scripts to examples/; rename
  untsructured_meta.py -> unstructured_meta.py

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Contexts
  ([`2c8b7e3`](https://github.com/arkitektio/mikro-server-next/commit/2c8b7e36bd7dc6f1bfc5ec9d0573cab9030b5433))

- Correct import statements for strawberry_django
  ([`6c0f7b4`](https://github.com/arkitektio/mikro-server-next/commit/6c0f7b4c0a3903bb6713c6ddfb438e5e27ebcb51))

- Correct key name for chunk shape in ZarrStore model
  ([`76b0f4c`](https://github.com/arkitektio/mikro-server-next/commit/76b0f4caa0ddd2f51f57de3253c7ba7f6c2f6379))

- Datalayer
  ([`b756437`](https://github.com/arkitektio/mikro-server-next/commit/b7564379aec5dfc5c6f6f2d8915f0e985d5b0b7c))

- Default dataset fixes
  ([`e6f160d`](https://github.com/arkitektio/mikro-server-next/commit/e6f160d4e8a92cfea62f4570fbe79b69f333afcf))

- Docker next building
  ([`20088a6`](https://github.com/arkitektio/mikro-server-next/commit/20088a6baec6ce4ed65a94f5f15d46c68abdb8c8))

- Enforce organization scoping on mutations, single-object queries and subscriptions
  ([`13c1772`](https://github.com/arkitektio/mikro-server-next/commit/13c1772f20ff316446164035f3129083d326d435))

- add core/scoping.py (for_org/get_for_org/aget_for_org) resolving each model's path to its
  organization; unscopable models are an explicit list - route all by-id fetches in mutations,
  queries, schema.py and subscriptions through the scoped helpers - stamp organization on
  camera/objective/mesh creates (non-null FK was missing -> IntegrityError) and scope
  ensure_*/update_or_create lookups - subscriptions: verify the parent object is visible before
  joining rooms, org-prefix the global rooms, centralize room names in core.channels, fix wrong
  rooms/channels and the dict-vs-signal message handling - settings_test: second static token in
  another org; add cross-org regression tests

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Filters
  ([`deb0f89`](https://github.com/arkitektio/mikro-server-next/commit/deb0f89ead81979bc8222335191042e5ea55a044))

- Initial tests
  ([`b860e49`](https://github.com/arkitektio/mikro-server-next/commit/b860e4983f2f8704e4c537a217c1472d3ebecf57))

- Keep model = input.to_pydantic() validation lines; make F841 advisory in CI
  ([`421b822`](https://github.com/arkitektio/mikro-server-next/commit/421b822ecd4881549d549846840abc212bcaf672))

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Long types
  ([`4d97832`](https://github.com/arkitektio/mikro-server-next/commit/4d978321e2d05fdb94f00e69301ec78667fa8758))

- Mikro_server
  ([`17a9818`](https://github.com/arkitektio/mikro-server-next/commit/17a9818995d3ac324a82c8aaec5142d541bb9ccc))

- Mor eshit
  ([`600e2af`](https://github.com/arkitektio/mikro-server-next/commit/600e2aff56f3d0b31c72dc4f98749247a5b56f48))

- More dataset features
  ([`645a1cd`](https://github.com/arkitektio/mikro-server-next/commit/645a1cde789dc2144dd3ce4e6feb9edcd66589ba))

- No nore stupid examples
  ([`dfa81b1`](https://github.com/arkitektio/mikro-server-next/commit/dfa81b14fc1d882640bebfa2f9b392c985ce5407))

- Region in parquest
  ([`0a17a47`](https://github.com/arkitektio/mikro-server-next/commit/0a17a477d49eee02b97addf6bbc29779bbd2ccfe))

- Rekuest
  ([`7232c4f`](https://github.com/arkitektio/mikro-server-next/commit/7232c4f97862819c671c1caeffda2d6042fa9cc2))

- Smaller refactor bug fixes
  ([`7966d7e`](https://github.com/arkitektio/mikro-server-next/commit/7966d7ef10b7d7ffdcb5255959bd472cdf3b2e3d))

- Stuff
  ([`ff4a302`](https://github.com/arkitektio/mikro-server-next/commit/ff4a302465f3966a12b62e5b770755409b22fe00))

- Stuff
  ([`1570a25`](https://github.com/arkitektio/mikro-server-next/commit/1570a258ed2ffda9956853e65d89669a0b86997a))

- Test
  ([`614f87e`](https://github.com/arkitektio/mikro-server-next/commit/614f87e60ac5611331ad5b67fe8aed37c9a4f801))

- Test parquet upload
  ([`591f407`](https://github.com/arkitektio/mikro-server-next/commit/591f4076b7a7118c6df12e42c53a717584af259c))

- Test_print_schema
  ([`1b5d483`](https://github.com/arkitektio/mikro-server-next/commit/1b5d483ef13c3efeda59580760acc0731e478981))

- The core refactor of filters
  ([`292bd8d`](https://github.com/arkitektio/mikro-server-next/commit/292bd8d01d99bf277d31fd8ac476443ae0a7c129))

- Trigger bulid and add secret key
  ([`8a9b634`](https://github.com/arkitektio/mikro-server-next/commit/8a9b634bda79cd370197e634f0f3c725dd2c84d4))

- Type names?
  ([`ca0bd83`](https://github.com/arkitektio/mikro-server-next/commit/ca0bd838b7c2a0a64cb800975381d8ad077c78ab))

- Update authentikate dependency to version 0.15
  ([`0676426`](https://github.com/arkitektio/mikro-server-next/commit/06764269d940eb4f194be8800c9afda3ea43cd58))

- Update context reference in file and roi subscription listeners
  ([`591d002`](https://github.com/arkitektio/mikro-server-next/commit/591d00259430e5314949d10dbfc758138abcde65))

- Update datalayer
  ([`f31563b`](https://github.com/arkitektio/mikro-server-next/commit/f31563b94fa7bc6f0034a9e82662871fa19583ca))

- Update Dockerfile to install poetry without root
  ([`78fb33e`](https://github.com/arkitektio/mikro-server-next/commit/78fb33ed1bf7a4c43182fe61ae2e7734cdfccf00))

- Update roi
  ([`0575a34`](https://github.com/arkitektio/mikro-server-next/commit/0575a3401f958a700ce0a5b84297e2a5145d74e2))

- Update to authentikate > 2
  ([`7de94a3`](https://github.com/arkitektio/mikro-server-next/commit/7de94a3e346b5302fed247916c22a9d822ea99e2))

- Update to new authentikate
  ([`ca740b5`](https://github.com/arkitektio/mikro-server-next/commit/ca740b5bcddcb59e622ef5416853428964683fd9))

- Uv.lock
  ([`bb43071`](https://github.com/arkitektio/mikro-server-next/commit/bb430712002da091cffd81a745d37a26c476cf22))

### Features

- Add custom field function with authentication permissions for GraphQL queries
  ([`2469f20`](https://github.com/arkitektio/mikro-server-next/commit/2469f209ae0f9d35289afb8946b3baca51d21cf4))

- Add date-range filters
  ([`eb9933d`](https://github.com/arkitektio/mikro-server-next/commit/eb9933dafba738013ce0e8175bb4d3a469e67809))

- Add delete mutation for histogram views and update related enums and types
  ([`18fff59`](https://github.com/arkitektio/mikro-server-next/commit/18fff59be3e34c68c042a6424528a8742df7e06c))

- Add docker dev workflow
  ([`9491aef`](https://github.com/arkitektio/mikro-server-next/commit/9491aef1f57695632cf7ba0226f25ca89406781b))

- Add HistogramView model and mutation for creating histogram views
  ([`deffbfd`](https://github.com/arkitektio/mikro-server-next/commit/deffbfd7cc11dbc434c8bedd3a3ac6532b9dda17))

- Add instrument organiztation
  ([`f196fc6`](https://github.com/arkitektio/mikro-server-next/commit/f196fc6c7bc78aaca12ec14722e3ba27ecea65af))

- Add more types
  ([`90ae179`](https://github.com/arkitektio/mikro-server-next/commit/90ae17948f77b1016baca7cd8f2addfe52c6406a))

- Add rekuest-compliant describe field
  ([`e2f50a9`](https://github.com/arkitektio/mikro-server-next/commit/e2f50a9147bddd1ab6bceafb5189a4ab085f1ca5))

- Add ROI ordering and history tracking to File model
  ([`42250bc`](https://github.com/arkitektio/mikro-server-next/commit/42250bceb59a20019cf40a4da344c7c102678534))

- Add second description field to Dataset model and update migrations
  ([`ea8077f`](https://github.com/arkitektio/mikro-server-next/commit/ea8077f031314887cf2266031f2d6027505b70c8))

- Add some table updates
  ([`23224a8`](https://github.com/arkitektio/mikro-server-next/commit/23224a8a966102317accfbe05a05a246e73c9a34))

- Add subscription for affine transformation view events
  ([`da6d6de`](https://github.com/arkitektio/mikro-server-next/commit/da6d6de287a91b615ef3ba55d23195d6dcd5bb80))

- Implemented the `affine_transformation_views` async generator function to handle subscriptions for
  affine transformation view events. - Created the `AffineTransformationViewEvent` type to represent
  create, delete, and update events. - Subscribed to the relevant channels and processed incoming
  messages to yield appropriate events based on the message content.

- Add tags field to Dataset model for enhanced tagging capabilities
  ([`079a7c1`](https://github.com/arkitektio/mikro-server-next/commit/079a7c11da610442a53175630b89dd9350a8a125))

- Add the organization features
  ([`fc92ea1`](https://github.com/arkitektio/mikro-server-next/commit/fc92ea1759b59f309cf9727a942457f193febb27))

- Add user authentication check in create_dataset function and include static tokens in AUTHENTIKATE
  settings
  ([`bd0acac`](https://github.com/arkitektio/mikro-server-next/commit/bd0acacba3e8d787f551627d7304533c13e4a125))

- Breaking config
  ([`b478a19`](https://github.com/arkitektio/mikro-server-next/commit/b478a19a81b4e1e15d84c69d5179200c81b812e5))

- Deleted som uneccsary models, remannts of the past
  ([`cd19716`](https://github.com/arkitektio/mikro-server-next/commit/cd1971682a6f96135f955cd2e81c5e468a67b5b0))

- Updated descriptions for scalar types in `core/scalars.py` to remove unnecessary line breaks and
  typos. - Consolidated `@strawberry.type` decorators in `core/types.py` for better readability. -
  Removed redundant line breaks and improved formatting in various sections of `core/types.py`. -
  Streamlined field definitions in `mikro_server/schema.py` for consistency and clarity. - Updated
  dependency version for `authentikate` in `pyproject.toml` and `uv.lock`. - Added new migration to
  `core/migrations` for `mediastore` model to include `file_name` and `mime_type` fields.

- Denormalize the creating task's assigner onto created objects
  ([`30b4017`](https://github.com/arkitektio/mikro-server-next/commit/30b40174799d2470b5177bda4ddc799eca1c022d))

The koherent Task table grows with every assignation, so filtering "objects assigned by user Y"
  through created_through scales with the user's task count. created_through_by (FK -> User,
  SET_NULL) stamps the assigner directly on the object at creation - a write-once fact, so the usual
  denormalization drift risk does not apply.

- created_through_by on all created_through-bearing models (and their historical shadows), stamped
  from the already-fetched task at every create site (task.assigner_id, no extra queries). -
  assignedBy filter now hits the denormalized indexed column instead of joining through the task
  table. - createdThroughBy exposed on the stamped GraphQL types. - Migration 0008 (verified forward
  and backward).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Enhance BigFileStore with filename and mime_type fields, add LocalHash model, and implement
  ensure_dataset mutation
  ([`a59f71d`](https://github.com/arkitektio/mikro-server-next/commit/a59f71d2da08ea5672ea33c7dfcde8a515b92681))

- Extend DatasetFilter with IDFilterMixin and SearchFilterMixin for enhanced filtering capabilities
  ([`dd56150`](https://github.com/arkitektio/mikro-server-next/commit/dd56150e883f2a3391831d40f46df40be48f2a65))

- First attempt at a stats field
  ([`1996d4b`](https://github.com/arkitektio/mikro-server-next/commit/1996d4b393df2f2c649a9a631437d9a13ed1546d))

- Major new things
  ([`bc84093`](https://github.com/arkitektio/mikro-server-next/commit/bc840932fcba5545f299ea7d331ee463b6a1d928))

- Major refactor
  ([`9bf0d74`](https://github.com/arkitektio/mikro-server-next/commit/9bf0d747e94cebe7a29a407ec2e51772039966fe))

- Oh more
  ([`1be9ff8`](https://github.com/arkitektio/mikro-server-next/commit/1be9ff8868f7726c055d82a0d1beb3a97410943f))

- Organization FK on every remaining model — full tenancy coverage
  ([`6a6d5e7`](https://github.com/arkitektio/mikro-server-next/commit/6a6d5e7c82202be711141c9460b71ecddf757622))

- Era, Experiment, MultiWellPlate, RenderTree, ROIGroup, Scene and ViewCollection get a required
  organization FK; core.scoping's UNSCOPED_MODELS escape hatch is now empty - DatalayerStore (and
  thus all polymorphic stores) gets a required organization FK; upload grant generators and finish_*
  take the organization id and stamp/scope the store, and request_*_access store lookups are
  org-filtered — closes the cross-org store claiming hole - creates stamp organization (era,
  multiwellplate, viewcollection, render_tree, scene, plus the 'Unknown' Era/Stage fallbacks); the
  RGBRenderContext fallback also gained its missing required image - hand-written migrations (core
  0006, datalayer 0002) add nullable, backfill (Era via its instrument, else first organization),
  then make non-null; exercised forward, backward and forward-with-legacy-rows on a scratch postgres
  — backfill verified - datalayer mutations: replaced getattr(input, "to_pydantic")() with the
  explicit call and removed stale 'del info' statements - SDL change: MultiWellPlate now exposes
  organization (same shape as Camera/Objective/Instrument already did); everything else unchanged

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Record the rekuest task objects were created through
  ([`4032467`](https://github.com/arkitektio/mikro-server-next/commit/4032467c84a8f540108ae7a4b6acb9e8cb1d6281))

With authentikate 2 every request can carry a validated Rekuest-Task header (task id, assigner, app,
  action, args). koherent 1 persists it as a Task row and links every history entry to it
  automatically; this adds the queryable, denormalized side in mikro:

- created_through FK (-> koherent.Task, SET_NULL) on all creator-bearing models: Image, Render
  (Blurhash/Video/Snapshot), Dataset, File, Table, Stage, Era, ROI, ADataset. - Every create
  mutation stamps created_through=get_or_create_task() explicitly; ensure_dataset passes it via
  defaults so tasks never fork a duplicate dataset; the default dataset helper forwards it. -
  GraphQL: Task type (with TaskFilter/TaskOrder, org-scoped tasks/task queries), createdThrough on
  stamped types, createdThroughTask and assignedBy filters via CreatedThroughFilterMixin, and
  ProvenanceEntry.during is replaced by ProvenanceEntry.task. - Migration 0007: swaps assignation_id
  for the task FK on historical tables and adds created_through (verified forward and backward).

Requires authentikate>=2.0.1 and koherent>=1.0.0 (local packages; release before deploying).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Recovery?
  ([`702de68`](https://github.com/arkitektio/mikro-server-next/commit/702de687d99c3a27223ae7e18ea98c835f633a03))

- Remove bot from anything
  ([`355d828`](https://github.com/arkitektio/mikro-server-next/commit/355d82879800d85a9bb9c07237b9d298f848bc63))

- Up up
  ([`70d2c55`](https://github.com/arkitektio/mikro-server-next/commit/70d2c55d7d44c29c3e4e4439d586d2827495cef6))

- Update authentikate
  ([`8e87a65`](https://github.com/arkitektio/mikro-server-next/commit/8e87a658d291bcf784f0c5a1a732c934753da483))

- Update authentikate
  ([`c85d20c`](https://github.com/arkitektio/mikro-server-next/commit/c85d20c702746b238454be1e12f6459a65e6ecba))

- Update default value for MY_SCRIPT_NAME in settings
  ([`7235e9a`](https://github.com/arkitektio/mikro-server-next/commit/7235e9a81f9a69f1a279e025d9771ac60a7ca253))

- Update request_file_upload and request_file_upload_presigned to handle default mime_type
  ([`b7eba0d`](https://github.com/arkitektio/mikro-server-next/commit/b7eba0d2fd401fc110c5ff3965146da3ea504fce))

- Update to latest kante
  ([`cc12121`](https://github.com/arkitektio/mikro-server-next/commit/cc12121d27e02c60d00227b577a9327bc3f05eda))

- Update to public key
  ([`67d1833`](https://github.com/arkitektio/mikro-server-next/commit/67d1833476afc444ea8399a3698220e9e32f7109))

- With provenance
  ([`4cdea47`](https://github.com/arkitektio/mikro-server-next/commit/4cdea476b0a7810fcd59fe7008e6e85f744a8274))

- With release workflow
  ([`9899ada`](https://github.com/arkitektio/mikro-server-next/commit/9899adace350d145e4bc3ecc620907195f9d19d5))

### Refactoring

- Clean up formatting and remove commented database configuration in settings
  ([`aba1980`](https://github.com/arkitektio/mikro-server-next/commit/aba198025e85dc6db6ae7c793d8c8096c06cb1c9))

- Factor repeated delete/pin mutations into _generic factories
  ([`2a3b8ad`](https://github.com/arkitektio/mikro-server-next/commit/2a3b8ad767433c41686606c59f125e61c831e49d))

- core/mutations/_generic.py: make_delete / make_pin build the resolver bodies as closures; every
  entity keeps its own GraphQL input type and its hand-written create/ensure mutations (explicit
  field mapping, no dynamic marshalling), so the SDL is byte-identical - pin_* is now implemented
  (pinned_by M2M toggle) for dataset, image, roi, era, stage, multi-well plate and mesh instead of
  raising NotImplementedError; entities without a pinned_by field keep their stubs - pinMesh fixed:
  previously took DeleteMeshInput and returned Snapshot (only intentional schema change) - ~40
  duplicate resolver bodies removed across 16 mutation modules

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Split core/models.py monolith into a domain-organized package
  ([`de9e880`](https://github.com/arkitektio/mikro-server-next/commit/de9e8806a28b5c3b7efce7ffa0a1b1fe76ed3a0d))

- core/models/ now has dataset, instrumentation, image, meta, stage, roi, view and adataset modules;
  __init__.py explicitly re-exports every name (including the datalayer stores the old monolith
  leaked) so 'from core import models' is unchanged everywhere - pure move: fields, Meta, helpers
  and class order preserved; verified by empty SDL diff, 'makemigrations --check' clean and 64
  passing tests - adds migration 0005 (related_name-only AlterFields) for pre-existing drift between
  models and migration 0004 that the --check gate exposed; no SQL impact

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

- Split core/types.py monolith into a domain-organized package
  ([`923f5cb`](https://github.com/arkitektio/mikro-server-next/commit/923f5cb0b0019fbf7168aac99dd449273ded79da))

- core/types/ now has auth, credentials, metadata, renders, mesh, instrumentation, acquisition,
  adataset and image modules; __init__.py explicitly re-exports all 93 public names so 'from core
  import types' is unchanged everywhere - the bidirectionally-referencing
  Image/View/ROI/Table/File/Dataset cluster stays together in image.py; seven cross-module
  back-references use strawberry.lazy('core.types.image') - pure move: SDL byte-identical, 64 tests
  pass, lint clean

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
