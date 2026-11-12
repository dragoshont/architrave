def customer_state(carrier_status):
    mapping = {"queued": "pending", "done": "approved", "lost": "exception"}
    return mapping.get(carrier_status, "approved")
