# Handling charges
Status: Accepted
Owner: Billing Operations
Effective: 2026-10-20

An outbound quote with one or more units has one flat 250-cent handling fee.
An empty or cancelled parcel has no fee. Units must be nonnegative integers;
reject negative and fractional inputs rather than rounding.

Insurance is a separate product. The carrier's declared value limit is not an
insurance pricing threshold. The insurance threshold, surcharge rate and
whether domestic/overseas rates differ remain undecided by Billing Operations.
