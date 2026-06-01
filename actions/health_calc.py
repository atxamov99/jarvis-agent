"""health_calc.py — BMI, BMR, calorie needs, ideal weight, water intake.

Inspired by: sukeesh/Jarvis (BMI/BMR), JARVIS-on-Messenger (health features)
All calculations are offline — no API needed.
"""


def _bmi(weight_kg: float, height_cm: float) -> tuple[float, str, str]:
    h_m  = height_cm / 100
    bmi  = weight_kg / (h_m ** 2)
    if bmi < 18.5:
        category, emoji = "Kam vazn", "⚠️"
    elif bmi < 25:
        category, emoji = "Normal vazn", "✅"
    elif bmi < 30:
        category, emoji = "Ortiqcha vazn", "⚠️"
    elif bmi < 35:
        category, emoji = "1-darajali semizlik", "🔴"
    elif bmi < 40:
        category, emoji = "2-darajali semizlik", "🔴"
    else:
        category, emoji = "3-darajali semizlik", "🔴"
    return bmi, category, emoji


def _bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    # Mifflin-St Jeor formula
    if gender.lower() in ("male", "erkak", "m"):
        return 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        return 10 * weight_kg + 6.25 * height_cm - 5 * age - 161


_ACTIVITY_MULTIPLIERS = {
    "sedentary":   (1.2,  "Harakatsiz (ofis ishi, mashq yo'q)"),
    "light":       (1.375, "Yengil faollik (haftada 1-3 kun mashq)"),
    "moderate":    (1.55,  "O'rtacha faollik (haftada 3-5 kun)"),
    "active":      (1.725, "Faol (haftada 6-7 kun og'ir mashq)"),
    "very_active": (1.9,   "Juda faol (professional sportchi/jismoniy ish)"),
}


def health_calc(parameters=None, response=None, player=None, session_memory=None) -> str:
    params   = parameters or {}
    action   = (params.get("action") or "bmi").lower().strip()
    weight   = float(params.get("weight", 70))    # kg
    height   = float(params.get("height", 175))   # cm
    age      = int(params.get("age", 25))
    gender   = (params.get("gender") or "male").strip()
    activity = (params.get("activity") or "moderate").strip().lower()

    if action in ("bmi", "vazn_indeks"):
        bmi, cat, emoji = _bmi(weight, height)
        ideal_low  = 18.5 * (height/100)**2
        ideal_high = 24.9 * (height/100)**2
        return (
            f"{emoji} **BMI (Tana Massa Indeksi)**\n"
            f"  Siz: {weight}kg, {height}cm\n"
            f"  BMI: **{bmi:.1f}** — {cat}\n"
            f"  Ideal vazn: {ideal_low:.1f}–{ideal_high:.1f} kg"
        )

    if action in ("bmr", "bazal", "metabolizm"):
        bmr = _bmr(weight, height, age, gender)
        return (
            f"🔥 **BMR (Bazal Metabolik Tezlik)**\n"
            f"  Siz: {weight}kg, {height}cm, {age}yosh, {gender}\n"
            f"  Kunlik minimum kaloriya: **{bmr:.0f} kcal**\n"
            f"  (Bu — mutlaq dam olganda yoqiladigan kaloriya)"
        )

    if action in ("calories", "kaloriya", "tdee"):
        bmr  = _bmr(weight, height, age, gender)
        mult, desc = _ACTIVITY_MULTIPLIERS.get(activity, _ACTIVITY_MULTIPLIERS["moderate"])
        tdee = bmr * mult
        return (
            f"🍽️ **Kunlik Kaloriya Ehtiyoji (TDEE)**\n"
            f"  Faollik darajasi: {desc}\n"
            f"  Saqlash uchun: **{tdee:.0f} kcal**\n"
            f"  Vazn yo'qotish: **{tdee-500:.0f} kcal** (sekin)\n"
            f"  Vazn olish: **{tdee+500:.0f} kcal** (asta)"
        )

    if action in ("water", "suv"):
        water_l = weight * 0.033
        return (
            f"💧 **Kunlik suv ehtiyoji**\n"
            f"  Vazningiz: {weight}kg\n"
            f"  Tavsiya: **{water_l:.1f} litr** ({water_l*4:.0f} stakan)"
        )

    if action in ("all", "hammasi"):
        bmi, cat, emoji = _bmi(weight, height)
        bmr  = _bmr(weight, height, age, gender)
        mult, _ = _ACTIVITY_MULTIPLIERS.get(activity, _ACTIVITY_MULTIPLIERS["moderate"])
        tdee = bmr * mult
        water = weight * 0.033
        return (
            f"🏥 **Sog'liq ko'rsatkichlari** ({weight}kg, {height}cm, {age}yosh)\n\n"
            f"{emoji} BMI: **{bmi:.1f}** — {cat}\n"
            f"🔥 BMR: **{bmr:.0f} kcal** (minimal)\n"
            f"🍽️ TDEE: **{tdee:.0f} kcal** (kunlik)\n"
            f"💧 Suv: **{water:.1f} litr** kuniga"
        )

    return f"Noma'lum amal: {action}. bmi|bmr|calories|water|all"
