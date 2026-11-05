"""Κωδικός Πληρωμής RF (RI18), DIAS-ORG02 Παράρτημα Β. Καθαρές συναρτήσεις.

Δομή (25 χαρακτήρες):  RF cc | ooooo (9nnnn) | u | pppppp | K dddddddd

- u: ψηφίο ελέγχου ποσού 0-7 (Β.2.2)· 8 = χωρίς έλεγχο ποσού (μόνο με K=3).
- pppppp: commercial partner.
- K: είδος. 1 παραγγελία, 2 τιμολόγιο, 3 πάγιος πελάτη (d = 0).
  Η υλοποίηση της v13 (lam_dias_rf) έβαζε εδώ πάντα 0 (id παραγγελίας με μηδενικά μπροστά, ή
  0 στον πάγιο)· K = 0 σημαίνει λοιπόν «κωδικός v13» και δεν αντιστοιχίζεται ποτέ αυτόματα.
"""
import re

PARTNER_DIGITS = 6
DOC_DIGITS = 8
USAGE_NO_AMOUNT = 8

KIND_V13 = 0
KIND_ORDER = 1
KIND_INVOICE = 2
KIND_PARTNER = 3


def clean(code):
    return re.sub(r'\s+', '', code or '').upper()


def amount_digit(total):
    """Β.2.2: ποσό σε λεπτά, συντελεστές 1,7,3 από δεξιά, mod 8."""
    cents = int(round(float(total) * 100))
    if cents < 0:
        raise ValueError('negative amount')
    weights = (1, 7, 3)
    return sum(int(d) * weights[i % 3] for i, d in enumerate(reversed(str(cents)))) % 8


def check_digits(body):
    """ISO 11649: σώμα + 'RF00' ως 271500, 98 - mod 97."""
    return '%02d' % (98 - int(body + '271500') % 97)


def make_rf(org5, partner_id, kind, doc_id=0, total=None):
    """Νέος κωδικός (v19). kind = KIND_ORDER / KIND_INVOICE με ποσό, KIND_PARTNER χωρίς."""
    org5 = str(org5 or '')
    if not re.fullmatch(r'9\d{4}', org5):
        raise ValueError('Ο Κωδικός Οργανισμού πρέπει να είναι της μορφής 9nnnn')
    partner_id, doc_id = int(partner_id or 0), int(doc_id or 0)
    if not 0 < partner_id < 10 ** PARTNER_DIGITS:
        raise ValueError('partner id εκτός ορίων')
    if kind == KIND_PARTNER:
        usage, doc_id = USAGE_NO_AMOUNT, 0
    elif kind in (KIND_ORDER, KIND_INVOICE):
        if not 0 < doc_id < 10 ** DOC_DIGITS:
            raise ValueError('id εγγράφου εκτός ορίων')
        if total is None:
            raise ValueError('απαιτείται ποσό')
        usage = amount_digit(total)
    else:
        raise ValueError('άγνωστο είδος κωδικού')
    body = '%s%d%0*d%d%0*d' % (org5, usage, PARTNER_DIGITS, partner_id, kind, DOC_DIGITS, doc_id)
    return 'RF' + check_digits(body) + body


def verify_rf(code):
    c = clean(code)
    return bool(re.fullmatch(r'RF\d{23}', c)) and int(c[4:] + '2715' + c[2:4]) % 97 == 1


def parse_rf(code):
    """dict με τα μέρη του κωδικού, ή None αν δεν είναι έγκυρος RI18 της δομής μας.
    Κωδικός v13 (K=0) επιστρέφεται με kind=KIND_V13· ο καλών αποφασίζει τι κάνει."""
    c = clean(code)
    if not verify_rf(c):
        return None
    usage, kind = int(c[9]), int(c[16])
    doc_id = int(c[17:25])
    info = {'code': c, 'org': c[4:9], 'usage': usage, 'partner_id': int(c[10:16]),
            'kind': kind, 'doc_id': doc_id}
    if kind == KIND_V13:
        return info
    if kind == KIND_PARTNER:
        ok = usage == USAGE_NO_AMOUNT and doc_id == 0
    elif kind in (KIND_ORDER, KIND_INVOICE):
        ok = usage < USAGE_NO_AMOUNT and doc_id > 0
    else:
        ok = False
    return info if ok and info['partner_id'] > 0 else None


def check_amount(info, total):
    """True αν το ποσό ταιριάζει με το ψηφίο χρήσης (ο πάγιος δεν ελέγχει ποσό)."""
    if info['usage'] == USAGE_NO_AMOUNT:
        return True
    try:
        return amount_digit(total) == info['usage']
    except (ValueError, TypeError):
        return False


def format_rf(code):
    c = clean(code)
    return ' '.join(c[i:i + 4] for i in range(0, len(c), 4))


def qr_value(code, total=None):
    """25 ψηφία, ή 36 με 11ψήφιο ποσό σε λεπτά."""
    c = clean(code)
    return c if total is None else c + '%011d' % int(round(float(total) * 100))
