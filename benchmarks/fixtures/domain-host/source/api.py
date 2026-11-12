from billing import handling_fee
from carrier import customer_state
from inventory import reserve


def quote(request):
    return {"handling_cents": handling_fee(request["units"], request.get("cancelled", False))}


def import_event(request):
    return {"state": customer_state(request["carrier_status"]), "raw": request["carrier_status"]}


def reserve_stock(request):
    return {"remaining": reserve(request["available"], request["quantity"])}
