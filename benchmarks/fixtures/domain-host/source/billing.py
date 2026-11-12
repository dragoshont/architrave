def handling_fee(units, cancelled=False):
    raise NotImplementedError("handling fee is not connected")


def insurance_charge(value_cents):
    raise NotImplementedError("insurance rate awaits business decision")


def insured_quote(value_cents, units):
    return handling_fee(units) + insurance_charge(value_cents)
