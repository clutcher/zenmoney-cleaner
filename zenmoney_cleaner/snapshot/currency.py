from dataclasses import dataclass

_USUAL_DECIMALS = 2
_DECIMALS_BY_CODE_MAP = {
    code: 0
    for code in ("BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND", "VUV", "XAF", "XOF", "XPF")
} | {code: 3 for code in ("BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND")}


@dataclass(frozen=True)
class Currency:
    code: str

    @property
    def decimals(self) -> int:
        return _DECIMALS_BY_CODE_MAP.get(self.code.upper(), _USUAL_DECIMALS)

    def round_amount(self, amount: float) -> float:
        if self.decimals == 0:
            return round(amount)

        return round(amount, self.decimals)

    def to_minor_units(self, amount: float) -> int:
        return round(amount * 10**self.decimals)
