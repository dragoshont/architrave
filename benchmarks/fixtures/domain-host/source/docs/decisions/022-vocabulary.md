# Status vocabulary
Status: Accepted
Owner: Parcel Desk

Customer parcel states are pending, delivered, awaiting_receipt, exception
and unknown. Unknown carrier values remain unknown; retain their raw value.
Approval belongs to Dispatch clearance, not carrier delivery.

Integration agreements define what each carrier's completion means.
Without an accepted agreement, do not infer delivery from the word "done".
