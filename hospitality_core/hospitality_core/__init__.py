# NOTE: this used to unconditionally import `hospitality_core.hospitality_core.patches`,
# which monkeypatched ERPNext's GL Entry party/account-type validation to a no-op for
# every doctype in the whole installation, permanently, on every process. That removed
# a real accounting safeguard globally to work around a narrow Front Desk payment
# permission issue. Removed — if that original issue resurfaces, fix it at its source
# (e.g. the account type configured in Hospitality Accounting Settings /
# `api/payment_bridge.py`) rather than disabling validation platform-wide again.
