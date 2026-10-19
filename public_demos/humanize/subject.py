from __future__ import annotations
_SUPERSCRIPT_MAP = {
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
    "-": "⁻",
}

_SUPERSCRIPT_TRANS = str.maketrans(_SUPERSCRIPT_MAP)

def _format_not_finite(value: float) -> str:
    """Utility function to handle infinite and nan cases."""
    import math

    if math.isnan(value):
        return "NaN"
    if math.isinf(value) and value < 0:
        return "-Inf"
    if math.isinf(value) and value > 0:
        return "+Inf"
    return ""

def scientific(value: NumberOrString, precision: int = 2) -> str:
    """Return number in string scientific notation z.wq x 10ⁿ.

    Examples:
        ```pycon
        >>> scientific(float(0.3))
        '3.00 x 10⁻¹'
        >>> scientific(int(500))
        '5.00 x 10²'
        >>> scientific(-1000)
        '-1.00 x 10³'
        >>> scientific(1000, 1)
        '1.0 x 10³'
        >>> scientific(1000, 3)
        '1.000 x 10³'
        >>> scientific("99")
        '9.90 x 10¹'
        >>> scientific("foo")
        'foo'
        >>> scientific(None)
        'None'

        ```

    Args:
        value (int, float, str): Input number.
        precision (int): Number of decimal for first part of the number.

    Returns:
        str: Number in scientific notation z.wq x 10ⁿ.
    """
    import math

    try:
        value = float(value)
        if not math.isfinite(value):
            return _format_not_finite(value)
    except (ValueError, TypeError):
        return str(value)
    fmt = f"{{:.{int(precision)}e}}"
    n = fmt.format(value)
    part1, part2 = n.split("e")
    # Normalise exponent: int() strips the "+" sign and leading zeros,
    # while preserving "-" and a single "0" for 10⁰.
    return part1 + " x 10" + str(int(part2)).translate(_SUPERSCRIPT_TRANS)

def metric(value: float, unit: str = "", precision: int = 3) -> str:
    """Return a value with a metric SI unit-prefix appended.

    Examples:
        ```pycon
        >>> metric(1500, "V")
        '1.50 kV'
        >>> metric(2e8, "W")
        '200 MW'
        >>> metric(220e-6, "F")
        '220 μF'
        >>> metric(1e-14, precision=4)
        '10.00 f'

        ```

    The unit prefix is always chosen so that non-significant zero digits are required.
    i.e. `123,000` will become `123k` instead of `0.123M` and `1,230,000` will become
    `1.23M` instead of `1230K`. For numbers that are either too huge or too tiny to
    represent without resorting to either leading or trailing zeroes, it falls back to
    `scientific()`.
    ```pycon
    >>> metric(1e40)
    '1.00 x 10⁴⁰'

    ```

    Args:
        value (int, float): Input number.
        unit (str): Optional base unit.
        precision (int): The number of digits the output should contain.

    Returns:
        str:
    """
    import math

    if not math.isfinite(value):
        return _format_not_finite(value)
    exponent = math.floor(math.log10(abs(value))) if value != 0 else 0

    if exponent >= 33 or exponent < -30:
        return scientific(value, precision - 1) + unit

    old_bucket = exponent // 3 * 3
    value /= 10**old_bucket
    digits = int(max(0, precision - exponent % 3 - 1))
    # Absorb a rounding carry (9.999 -> 10.0) by bumping the exponent.
    if exponent < 32 and round(abs(value), digits) >= 10 ** (exponent % 3 + 1):
        exponent += 1
        new_bucket = exponent // 3 * 3
        value /= 10 ** (new_bucket - old_bucket)
        digits = int(max(0, precision - exponent % 3 - 1))

    if exponent >= 3:
        ordinal_ = "kMGTPEZYRQ"[exponent // 3 - 1]
    elif exponent < 0:
        ordinal_ = "mμnpfazyrq"[(-exponent - 1) // 3]
    else:
        ordinal_ = ""
    value_ = format(value, f".{digits}f")
    if not (unit or ordinal_) or unit in ("°", "′", "″"):
        space = ""
    else:
        space = " "

    return f"{value_}{space}{ordinal_}{unit}"
