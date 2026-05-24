"""password_gen.py — Generate secure random passwords and PINs."""
import secrets
import string


_SETS = {
    "letters":    string.ascii_letters,
    "digits":     string.digits,
    "symbols":    string.punctuation,
    "alphanumeric": string.ascii_letters + string.digits,
    "all":        string.ascii_letters + string.digits + string.punctuation,
}


def password_gen(parameters=None, response=None, player=None, session_memory=None) -> str:
    params  = parameters or {}
    mode    = (params.get("mode") or "password").lower().strip()
    length  = int(params.get("length", 16))
    count   = min(int(params.get("count", 1)), 10)
    charset = params.get("charset", "all").lower().strip()

    if mode in ("pin", "raqam"):
        pins = [secrets.token_hex(4)[:length].upper() if charset == "hex"
                else "".join(secrets.choice(string.digits) for _ in range(length))
                for _ in range(count)]
        result = "\n".join(pins)
        label  = f"{length}-xonali PIN"

    elif mode in ("passphrase", "ibora"):
        # Random word-like syllables: easier to remember
        syllables = ["ma","ka","li","ro","bu","si","de","no","ta","vi",
                     "po","la","ki","re","mu","so","da","ni","to","va"]
        words = []
        for _ in range(count):
            n_words = max(3, length // 5)
            phrase = "-".join("".join(secrets.choice(syllables) for _ in range(3))
                              for _ in range(n_words))
            words.append(phrase)
        result = "\n".join(words)
        label  = "parol-ibora"

    else:
        chars = _SETS.get(charset, _SETS["all"])
        # Guarantee at least one char from each requested category for "all"
        passwords = []
        for _ in range(count):
            if charset == "all":
                mandatory = [
                    secrets.choice(string.ascii_uppercase),
                    secrets.choice(string.ascii_lowercase),
                    secrets.choice(string.digits),
                    secrets.choice(string.punctuation),
                ]
                rest = [secrets.choice(chars) for _ in range(max(0, length - 4))]
                pool = mandatory + rest
                secrets.SystemRandom().shuffle(pool)
                passwords.append("".join(pool[:length]))
            else:
                passwords.append("".join(secrets.choice(chars) for _ in range(length)))
        result = "\n".join(passwords)
        label  = f"{length} belgili parol"

    if player:
        player.write_log(f"[PasswordGen] {label} x{count}")
    return f"{label} ({count} ta):\n{result}"
