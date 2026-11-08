# Tessera-Shaped LongBuild Fixture

This frozen, synthetic fixture exercises a persistent backend, Web, Electron,
iOS, a provider boundary, sandbox deployment state, and product-level checks.
It contains no private Tessera source or data.

The baseline is intentionally inconsistent. The benchmark task is complete only
when all surfaces consume the contract in `docs/product-contract.md`, deployment
state matches the release, provider authentication remains an explicit external
checkpoint, and `python3 tests/verify.py` passes.