# Stock reservation
Status: Accepted
Owner: Store Operations

Reserve a positive integer quantity from a nonnegative integer available
balance, never more than is available. The operation returns the remaining
balance without changing its inputs.

Functional modules are the chosen design for these adapters. The storefront
cart operation is all-or-nothing from its caller's perspective: invalid carts
throw and leave the input stock untouched. Cross-process storage serialization
is owned by the upstream service; this repository does not establish its
transaction protocol.
