"""Pure duplicate-vehicle decisions shared by runtime code and tests."""

VALID_POLICIES = {"threshold", "sell_all", "keep_all"}


def decide_duplicate_action(policy, price, threshold):
    """Return (action, ocr_failed); unknown prices are never sold implicitly."""
    if policy not in VALID_POLICIES:
        raise ValueError(f"未知重复车策略: {policy}")
    if policy == "sell_all":
        return "sell", price is None
    if policy == "keep_all":
        return "keep", False
    if price is None:
        return "keep", True
    return ("keep" if price > threshold else "sell"), False
