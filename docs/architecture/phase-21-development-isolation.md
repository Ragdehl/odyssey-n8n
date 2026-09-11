# Phase 21 — Production/development isolation

Status: 21A architecture challenge complete; 21B transient proof complete; 21C complete; 21D next.

## Objective

Allow ordinary Odyssey development and deterministic testing without a realistic path to
mutate production personal knowledge or the production product flow. Production remains
the stable `main` deployment and `/data/odyssey` remains production-only.

## 21A decision

Use a separate source checkout, separate vault/state/runtime/index roots, and a separate
runtime for development. Development uses synthetic or disposable data by default. A
separate n8n development instance is a candidate later boundary when browser/workflow
testing justifies it, not a requirement by symmetry. No public development route is
required for the initial proof. Do not introduce a permanent `develop` branch unless
repeated integration work justifies it.

## Operator model and DEV deployment identity

The persistent DEV environment and Git branch model are separate concerns. Odyssey should
provide a fixed development product identity without requiring the operator to switch
variables, roots, ports, or Git branches manually.

Target operator experience:

```text
PROD                                  DEV
odyssey.ragdehl.com                   dev.odyssey.ragdehl.com (when mobile access is enabled)
main / explicit production release    currently deployed development commit
/data/odyssey                         /data/odyssey-dev
production runtime                    development runtime
production n8n boundary               development n8n boundary when justified
real personal knowledge               synthetic/non-personal knowledge
```

The development environment may deploy the active feature branch/worktree directly. A
long-lived `dev` branch is therefore optional, not required to obtain a stable DEV product.
The deployed DEV front end, runtime/backend code, and checked-in n8n workflow source should
come from the same Git commit whenever those layers are under test together. Deployment
and status evidence should expose that commit so drift is visible.

Normal development should look like:

```text
feature branch / worktree
        |
        v
explicit DEV deploy
        |
        v
open fixed DEV URL and test front + backend + workflow together
        |
        v
PR / human merge to main
        |
        v
explicit production promotion/deploy
```

The user should switch between PROD and DEV by opening different fixed product endpoints,
not by reconfiguring Odyssey. The DEV UI should carry an unmistakable visual DEV marker
when browser access is enabled. Production promotion remains explicit; merging source must
not silently mutate production.

## 21B contract

Acceptance requires:

- fixed, independently resolved DEV source/data roots with a fail-closed check against
  `/data/odyssey`;
- concurrent production and DEV health/listening boundaries on different private ports;
- an offline deterministic DEV read/write and index rebuild using only synthetic data;
- production vault, state, indexes, runtime, n8n identity/version, and resource boundaries
  unchanged by the proof;
- transient DEV runtime stopped after the proof, with coherent DEV checkout/data retained;
- no provider calls, public routing, credentials, n8n changes, or persistent DEV service.

Out of scope: changing production, creating DEV n8n or external routing, changing systemd,
Docker, Cloudflare, credentials, network/security configuration, or deploying/merging.

## Observed 21B evidence

The DEV source worktree is `/home/ragdehl/projects/odyssey-dev`, branch
`phase21-isolated-development`, based on merged `origin/main` `4efdabc19d824741bf5029e6dcb04e9754d0aa8f`.
The persistent-looking target `/data/odyssey-dev` could not be created because the host
denied creation under `/data`; the bounded proof therefore used the fixed disposable root
`/tmp/odyssey-21b`. Its mutable roots were:

```text
vault           /tmp/odyssey-21b/vault
state/pending   /tmp/odyssey-21b/state/pending
runtime         /tmp/odyssey-21b/runtime
embedding cache /tmp/odyssey-21b/runtime/embedding-cache
schema          /home/ragdehl/projects/odyssey-dev/config/note-schema.json
```

The root guard passed: no DEV mutable root was equal to or below `/data/odyssey`.
The DEV vault has its own empty baseline commit
`2dfa0e7fd227fb0a7714a85db48a6726b07c6fb5`, followed by synthetic sentinel
commit `5ea35e5` for `people/Dev Phase 21B Sentinel.md`. Context and semantic rebuilds
each indexed one note. The transient runtime used `127.0.0.1:28765` and was served by
`odyssey-phase21b-dev-runtime.service` (PID 212313); it returned HTTP 200 on `/healthz`
while production remained on `172.18.0.1:8765` (PID 202011), also HTTP 200. The DEV
runtime was stopped after verification; production was not restarted.

Before/after production invariants were unchanged: vault HEAD
`0a87fed0e4386c4913fa3be1035611eba1af7107`, clean status, canonical Markdown SHA256
`aed19f725ee9702b7e9cc64a4e2cae997215157fee3f1b027565d0b610732bb8`, empty pending
state, unchanged `context.sqlite3` and `semantic.sqlite3` mutation detectors, production
runtime PID/listener/health, n8n workflow `hMbt07KRz8HVDOUO` active version
`7c1df175-e9b2-466d-91c4-fa0f15a0e431`, and n8n container identity.

The concurrent observation was 4 GiB RAM with about 1.5 GiB available, about 1.8 GiB
swap free, load `0.48 0.26 0.10`, production RSS about 646 MiB, and DEV RSS about
631 MiB. Readings fluctuate; this proves concurrency but does not establish a precise
incremental capacity budget. The DEV worktree initially lacked its own `.venv`; using
the existing immutable production dependency environment did not cross data roots, but
21C should provide explicit DEV deploy/start/stop/status operations and a persistent DEV
root.

## Observed 21C evidence

The persistent DEV data root is `/data/odyssey-dev`, created with user ownership and
mode `750`, separate from `/data/odyssey`. It contains only `vault/`, `state/pending/`,
and `runtime/` (including the DEV-only embedding cache). The DEV vault has its own exact
Git root and history: empty baseline `578342c6147607c0e568fc7b9ac0ffc35a54428c`, then
synthetic-only sentinel commit `c498ae2ac31844b0b216c782eaa7340abcfd0b54` and persistent
sentinel commit `0012eefcedfe3590ce5398fe04c2b13e165367b3`. No production Markdown was
copied.

The DEV source executes from `/home/ragdehl/projects/odyssey-dev/.venv/bin/python`.
This is a separate venv with an explicit read-only `.pth` reference to the already
installed local dependency packages; the production venv itself was not modified. The
tracked `scripts/odyssey-dev` command and `deploy/odyssey-dev-runtime.service` define
fixed roots, actor, host, and port. The command's root guard rejects escapes or overlap
with `/data/odyssey`; the service wrapper invokes the same guard before starting Core.

The persistent user service is `odyssey-dev-runtime.service` on `127.0.0.1:28765`.
`odyssey-dev deploy` requires a clean DEV source checkout, restarts only this unit,
waits for health, and records the exact successful source commit in
`/data/odyssey-dev/runtime/deployed-commit`. `start`, `stop`, `restart`, and `status`
use the same fixed identity without manual environment or branch switching. A host
entrypoint is installed at `~/.local/bin/odyssey-dev` as a symlink to the tracked command.

The offline proof wrote/read the synthetic `dev-phase21c-persistent-sentinel`, rebuilt
both indexes with two notes, stopped DEV, started it again, and read the note after
restart. Both context and semantic indexes contained two note rows; both DEV health
probes returned HTTP 200. The deployed source identity was
`75bfd623c1b6a21b668c78db76dab6aec464934c` during the proof.

With production and DEV active, observed resources were 4 GiB RAM with about 1.5 GiB
available, 1.5 GiB swap free, load `0.84 0.51 0.23`, production runtime RSS about
538 MiB, DEV runtime RSS about 649 MiB, n8n process RSS about 302 MiB plus task runner
about 88 MiB, and cloudflared about 35 MiB. Docker's memory-limit display was
unavailable (`0B`), so RSS is the usable comparison. On this evidence the decision is
**HOLD_DEV_N8N**: the DEV runtime alone adds substantial memory and swap pressure on a
4 GiB host, while browser/workflow value can be evaluated after the fixed private DEV
runtime is operational. Revisit with measured demand and a capacity margin before adding
another n8n instance.

Production remained unchanged: vault HEAD
`0a87fed0e4386c4913fa3be1035611eba1af7107`, canonical Markdown SHA256
`aed19f725ee9702b7e9cc64a4e2cae997215157fee3f1b027565d0b610732bb8`, clean status,
empty pending state, context/semantic hashes unchanged, runtime PID `202011` and
listener/health unchanged, n8n container identity unchanged, and no production command
or service was restarted. No provider/model/API call was made.

## 21D gate

If browser/workflow integration requires it, evaluate a synchronized DEV n8n/routing
pilot under the `HOLD_DEV_N8N` capacity decision. Any implementation must verify fixed
PROD/DEV identities, preserve the endpoint-based operator model, and prove production
invariants before and after. The current 21C command surface is the deployment boundary;
it does not yet create external routing or a DEV n8n instance.
