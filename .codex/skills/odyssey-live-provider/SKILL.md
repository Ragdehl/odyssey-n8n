---
name: odyssey-live-provider
description: Safely access authorized live OpenAI models or diagnose a missing OPENAI_API_KEY in Odyssey's Raspberry environment. Use before billable real-provider tests; never request replacement credentials simply because a Remote Desktop shell lacks them.
---

# Odyssey live LLM credentials and cost

1. Check **explicit authorization**, model/reasoning, call count, estimated cap and synthetic-vault scope. A request to edit or test code is not unlimited approval for paid calls.
2. A normal Remote Desktop terminal intentionally lacks `OPENAI_API_KEY`. This does **not** mean the key is absent. The protected source is `/home/ragdehl/.config/odyssey/secrets.env`, a systemd `EnvironmentFile`. Check file existence/readability and `systemd --user` manager **without reading or printing any value**.
3. Prefer a **transient systemd user unit** with the fixed EnvironmentFile, `--wait --collect --pipe` and an explicit bounded gate authorization flag. User manager on the Pi may require `XDG_RUNTIME_DIR=/run/user/1000` and `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`.
4. Never source the protected file into the shared shell, dump environment, paste keys, copy .env, persist a unit containing a key, or log/hash/tokenize actual credentials. The n8n/Cloudflare environment is separate. If the manager or fixed source is inaccessible, stop instead of inventing a path.
5. Confirm the actual **Odyssey production capability model** (not the Codex developer model), effort, strict schema, max output, timeout, approval flag and budget before the call. Fake schema checks and frozen replay first; one scoped authorized live gate when needed.
6. Record only model/configuration, SHA, nonsecret status, cost estimate and redacted evidence. Core/E3 still decides mutations; provider text never directly authorizes a write.

**Concrete read-only preflight** (does not run an LLM and never prints the key):

```bash
test -r /home/ragdehl/.config/odyssey/secrets.env
XDG_RUNTIME_DIR=/run/user/1000 \
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
systemctl --user show --property=Version
```

**Nonbillable unit wiring check**, only if diagnosing the unit mechanism (the payload is `/usr/bin/true`, not a model call):

```bash
XDG_RUNTIME_DIR=/run/user/1000 \
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
systemd-run --user --wait --collect --pipe \
  --property=EnvironmentFile=/home/ragdehl/.config/odyssey/secrets.env \
  /usr/bin/true
```

For a real gate replace `/usr/bin/true` **only after** explicitly verifying the actual script, approval environment flag, budget, model and data scope. Never infer authorization from this template. See `docs/infrastructure/raspberry-runtime.md`; manual shell sourcing is superseded.
