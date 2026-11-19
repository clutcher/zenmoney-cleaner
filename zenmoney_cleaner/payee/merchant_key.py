import re


class MerchantKeyMaker:
    def __init__(self, strip_patterns: tuple[re.Pattern[str], ...]) -> None:
        self._strip_patterns = strip_patterns

    def make_key(self, payee: str) -> str | None:
        stripped_payee = payee
        for pattern in self._strip_patterns:
            stripped_payee = pattern.sub("", stripped_payee)

        merchant_key = " ".join(stripped_payee.upper().split())
        return merchant_key or None
