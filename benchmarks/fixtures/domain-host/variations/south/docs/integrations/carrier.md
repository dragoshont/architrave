# South handoff agreement
Status: Accepted
Owner: Parcel Desk Integrations
Context: South carrier, customer tracking API

"queued" means pending. "done" records depot handoff, not recipient delivery:
the customer state must be awaiting_receipt. Only "signed" means delivered.
"lost" means exception. Unknown vendor values must remain unknown.
The North recipient-scan agreement is not applicable to this integration.
