"""unit_converter.py — Comprehensive unit conversion (length, mass, temp, speed, volume, area, data).

Inspired by: sukeesh/Jarvis (unit conversions), swapagarwal/JARVIS-on-Messenger (binary/hex/length/mass/speed/temp/time)
All offline — no API needed.
"""

_UNITS = {
    "length": {
        "m": 1.0, "meter": 1.0, "metr": 1.0,
        "km": 1000, "kilometer": 1000, "kilometers": 1000, "kilometr": 1000,
        "cm": 0.01, "centimeter": 0.01, "santimetr": 0.01,
        "mm": 0.001, "millimeter": 0.001,
        "ft": 0.3048, "foot": 0.3048, "feet": 0.3048, "fut": 0.3048,
        "in": 0.0254, "inch": 0.0254, "dyuym": 0.0254,
        "mi": 1609.344, "mile": 1609.344, "miles": 1609.344, "milya": 1609.344,
        "yd": 0.9144, "yard": 0.9144,
        "nm": 1e-9, "nanometer": 1e-9,
        "um": 1e-6, "micrometer": 1e-6,
        "ly": 9.461e15, "light_year": 9.461e15,
    },
    "mass": {
        "kg": 1.0, "kilogram": 1.0, "kilogramm": 1.0,
        "g": 0.001, "gram": 0.001, "gramm": 0.001,
        "mg": 1e-6, "milligram": 1e-6,
        "lb": 0.453592, "lbs": 0.453592, "pound": 0.453592, "pounds": 0.453592, "funt": 0.453592,
        "oz": 0.0283495, "ounce": 0.0283495, "untsiya": 0.0283495,
        "t": 1000, "ton": 1000, "tonna": 1000,
        "st": 6.35029, "stone": 6.35029,
        "ug": 1e-9, "microgram": 1e-9,
    },
    "speed": {
        "mps": 1.0, "m/s": 1.0,
        "kmh": 1/3.6, "km/h": 1/3.6, "kph": 1/3.6,
        "mph": 0.44704, "mi/h": 0.44704,
        "fps": 0.3048, "ft/s": 0.3048,
        "knot": 0.514444, "kn": 0.514444,
        "mach": 340.3,
    },
    "volume": {
        "l": 1.0, "liter": 1.0, "litr": 1.0,
        "ml": 0.001, "milliliter": 0.001, "millilitr": 0.001,
        "m3": 1000, "cubic_meter": 1000,
        "cm3": 0.001, "cubic_centimeter": 0.001,
        "gal": 3.78541, "gallon": 3.78541, "gallon_us": 3.78541,
        "fl_oz": 0.0295735, "fluid_ounce": 0.0295735,
        "cup": 0.236588,
        "tbsp": 0.0147868, "tablespoon": 0.0147868,
        "tsp": 0.00492892, "teaspoon": 0.00492892,
        "pt": 0.473176, "pint": 0.473176,
        "qt": 0.946353, "quart": 0.946353,
    },
    "area": {
        "m2": 1.0, "sqm": 1.0, "square_meter": 1.0,
        "km2": 1e6, "square_kilometer": 1e6,
        "cm2": 0.0001, "square_centimeter": 0.0001,
        "ha": 10000, "hectare": 10000, "gektar": 10000,
        "acre": 4046.86,
        "ft2": 0.092903, "sqft": 0.092903, "square_foot": 0.092903,
        "mi2": 2.59e6, "square_mile": 2.59e6,
    },
    "data": {
        "b": 1.0, "bit": 1.0,
        "byte": 8, "B": 8,
        "kb": 1000, "kilobit": 1000,
        "KB": 8000, "kilobyte": 8000,
        "mb": 1e6, "megabit": 1e6,
        "MB": 8e6, "megabyte": 8e6,
        "gb": 1e9, "gigabit": 1e9,
        "GB": 8e9, "gigabyte": 8e9,
        "tb": 1e12, "terabit": 1e12,
        "TB": 8e12, "terabyte": 8e12,
    },
}


def _convert_temp(value: float, frm: str, to: str) -> float:
    # Normalize to Celsius first
    frm = frm.lower().strip()
    to  = to.lower().strip()
    if frm in ("c", "celsius", "celcius"):
        c = value
    elif frm in ("f", "fahrenheit"):
        c = (value - 32) * 5/9
    elif frm in ("k", "kelvin"):
        c = value - 273.15
    elif frm in ("r", "rankine"):
        c = (value - 491.67) * 5/9
    else:
        raise ValueError(f"Noma'lum harorat birligi: {frm}")

    if to in ("c", "celsius"):
        return c
    elif to in ("f", "fahrenheit"):
        return c * 9/5 + 32
    elif to in ("k", "kelvin"):
        return c + 273.15
    elif to in ("r", "rankine"):
        return (c + 273.15) * 9/5
    else:
        raise ValueError(f"Noma'lum harorat birligi: {to}")


def _detect_category(unit: str) -> str | None:
    u = unit.lower().strip()
    for cat, units in _UNITS.items():
        if u in {k.lower() for k in units}:
            return cat
    return None


def _number_base(value_str: str, frm: str, to: str) -> str:
    frm = frm.lower(); to = to.lower()
    bases = {"binary": 2, "bin": 2, "ikkilik": 2,
             "octal": 8, "oct": 8, "sakkizlik": 8,
             "decimal": 10, "dec": 10, "o'nlik": 10,
             "hex": 16, "hexadecimal": 16, "o'n_oltilik": 16}
    if frm not in bases or to not in bases:
        return ""
    num = int(value_str, bases[frm])
    if bases[to] == 2:  return bin(num)
    if bases[to] == 8:  return oct(num)
    if bases[to] == 10: return str(num)
    if bases[to] == 16: return hex(num)
    return ""


def unit_converter(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    value_raw = str(params.get("value", "1")).strip()
    frm       = (params.get("from") or params.get("from_unit") or "").strip().lower()
    to        = (params.get("to")   or params.get("to_unit")   or "").strip().lower()
    category  = (params.get("category") or "").strip().lower()

    if not frm or not to:
        return "from va to parametrlarini kiriting. Masalan: value=100, from=km, to=mi"

    # Number base conversion
    base_result = _number_base(value_raw, frm, to)
    if base_result:
        return f"🔢 {value_raw} ({frm}) → **{base_result}** ({to})"

    try:
        value = float(value_raw)
    except ValueError:
        return f"Noto'g'ri qiymat: {value_raw}"

    # Temperature (special handling)
    temp_units = {"c", "f", "k", "r", "celsius", "fahrenheit", "kelvin", "celcius"}
    if frm in temp_units or to in temp_units:
        try:
            result = _convert_temp(value, frm, to)
            return f"🌡️ {value}{frm.upper()} = **{result:.4g}°{to.upper()}**"
        except ValueError as e:
            return str(e)

    # Regular units
    cat = category or _detect_category(frm)
    if not cat:
        return f"'{frm}' birligini aniqlab bo'lmadi. Kategoriyani ko'rsating (length/mass/speed/volume/area/data)."

    units = _UNITS.get(cat, {})
    frm_key = next((k for k in units if k.lower() == frm), None)
    to_key  = next((k for k in units if k.lower() == to),  None)

    if not frm_key:
        return f"'{frm}' birligi {cat} kategoriyasida topilmadi."
    if not to_key:
        return f"'{to}' birligi {cat} kategoriyasida topilmadi."

    in_base = value * units[frm_key]
    result  = in_base / units[to_key]

    # Smart formatting
    if result >= 1e9 or result <= 1e-6:
        fmt = f"{result:.6e}"
    elif result >= 1000:
        fmt = f"{result:,.4g}"
    elif result >= 0.001:
        fmt = f"{result:.6g}"
    else:
        fmt = f"{result:.6e}"

    emoji_map = {"length": "📏", "mass": "⚖️", "speed": "💨", "volume": "🥤", "area": "📐", "data": "💾"}
    emoji = emoji_map.get(cat, "🔄")
    return f"{emoji} {value} {frm_key} = **{fmt} {to_key}** ({cat})"
