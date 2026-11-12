# Parcel desk

The desk quotes parcel handling, reserves stock and imports carrier updates.
Python modules expose the desk API; `storefront.ts` is a functional storefront
adapter. `Dispatch` is the separately deployed .NET clearance service.

Business decisions live in `docs/decisions`, with integration-specific
agreements in `docs/integrations`. An accepted integration agreement overrides
generic vocabulary only in its named context. Proposals and meeting notes do
not override accepted decisions. Superseded decisions are historical evidence.

Use the existing public functions and console JSON input/output contracts.
No third-party packages are needed. Dispatch targets .NET 10; the storefront
can execute with Node's TypeScript stripping.
