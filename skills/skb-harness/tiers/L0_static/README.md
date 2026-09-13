# Tier L0 — Static Checks

Static checks delegate to each consuming skill's own L0 validators (e.g., `skb-repository-setup/harness/tiers/L0_static/`).
The harness dispatcher (`runtime/dispatch.py`) routes `--tier L0 --mode validate-only` through the skill's entrypoint;
this directory is reserved for **harness-internal** L0 checks (manifest schema, workflow TTL structural sanity).

Currently empty placeholder. SPEC §6.2.
