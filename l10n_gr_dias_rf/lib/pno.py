"""Αρχεία πληρωμών ΔΙΑΣ (PNO): ανάλυση και ονόματα αρχείων. Καθαρές συναρτήσεις.
Βάση: lam_dias_rf (v13), με απόρριψη χρεώσεων, αντιλογισμών και μη-EUR (συμβούλιο v2)."""
import csv
import io
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta


def to_str_date(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return (str(v).strip()[:10] if v else False) or False


def to_float(v):
    if v is None or v == '':
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    return float(s.replace('.', '').replace(',', '.')) if ',' in s else float(s)


def _strip_ns(text):
    text = re.sub(r'<\?xml[^>]*\?>', '', text)
    text = re.sub(r'\sxmlns(:\w+)?="[^"]*"', '', text)
    return re.sub(r'<(/?)[A-Za-z0-9_]+:', r'<\1', text)


def parse_xml(content):
    """.XOO (DIASMCTFH + camt.054.001.03, Παράρτημα Γ.1.1) → λίστα γραμμών με τα κλειδιά του CSV.
    Περιλαμβάνει και όσες ήρθαν online (RptgSrc/Prtry = 'DIAS OR'): το ίδιο RID δεν
    καταχωρείται δεύτερη φορά. Επιστρέφει (rows, skipped)."""
    text = content.decode('utf-8-sig', 'replace') if isinstance(content, bytes) else content
    root = ET.fromstring('<root>%s</root>' % _strip_ns(text))

    def tx(el, path):
        n = el.find(path)
        return (n.text or '').strip() if n is not None and n.text else ''

    tst = tx(root, './/TstCode')
    rows, skipped = [], 0
    for nt in root.iter('Ntfctn'):
        online = tx(nt, './RptgSrc/Prtry') == 'DIAS OR'
        for ntry in nt.findall('./Ntry'):
            if tx(ntry, './CdtDbtInd').upper() == 'DBIT' or tx(ntry, './RvslInd').lower() == 'true':
                skipped += sum(1 for _d in ntry.iter('TxDtls')) or 1
                continue
            bk = tx(ntry, './ValDt/Dt') or tx(ntry, './BookgDt/Dt')
            for d in ntry.iter('TxDtls'):
                amt = d.find('./Amt')
                ccy = (amt.get('Ccy') if amt is not None else '') or 'EUR'
                if tx(d, './CdtDbtInd').upper() == 'DBIT' or ccy.upper() != 'EUR':
                    skipped += 1
                    continue
                ustrd = tx(d, './/RmtInf/Ustrd') or tx(d, './/RmtInf/Strd/CdtrRefInf/Ref')
                rows.append({
                    'RID': tx(d, './Refs/InstrId'),
                    'RI_MID': ustrd[:25].strip(),
                    'RemittanceInformation': ustrd,
                    'PaidAmount': tx(d, './Amt'),
                    'BkDate': bk,
                    'PaymentDtTm': tx(d, './/RltdDts/AccptncDtTm'),
                    'DebtorName': tx(d, './/RltdPties/Dbtr/Nm'),
                    'DebtorBankBIC': tx(d, './/RltdAgts/DbtrAgt/FinInstnId/BICFI'),
                    'TransactionID': tx(d, './Refs/TxId'),
                    'Status': '0',
                    '_TstCode': tst,
                    '_Online': online,
                })
    return [r for r in rows if r['RID']], skipped


def is_xml(filename, content):
    return (filename or '').lower().endswith(('.xoo', '.xml')) or \
        (content or b'').lstrip()[:1] == b'<'


def parse_pno(filename, content):
    """(rows, skipped) από .XOO/.xml, .csv (cp1253 ή utf-8, ';') ή .xlsx."""
    if is_xml(filename, content):
        return parse_xml(content)
    name = (filename or '').lower()
    if name.endswith('.csv'):
        try:
            text = content.decode('cp1253')
        except UnicodeDecodeError:
            text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text.lstrip('﻿')), delimiter=';')
        rows = [{k.strip(): v for k, v in r.items() if k} for r in reader]
    elif name.endswith(('.xlsx', '.xlsm')):
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h else '' for h in next(it)]
        rows = [dict(zip(header, r)) for r in it]
    else:
        raise ValueError('Υποστηρίζονται αρχεία .XOO/.xml, .csv και .xlsx.')
    rows = [r for r in rows if str(r.get('LobID') or '').strip().lower() != 'eof' and r.get('RID')]
    return rows, 0


def pno_filenames(org, today, cycles, ext='xml', lobid=None, days_back=4):
    """Υποψήφια ονόματα: XOO → DPG<org><yymmdd><κύκλος>.XOO, αλλιώς
    DPG<OrgID><yyyymmdd><κύκλος>[.<LobID>].PNO.<ext>. Τα παλαιότερα πρώτα."""
    cyc = sorted({c.strip().zfill(2) for c in (cycles or '01,02').split(',') if c.strip()})
    names = []
    for back in range(days_back, -1, -1):
        day = today - timedelta(days=back)
        for c in cyc:
            if (ext or 'xml').lower() == 'xml':
                names.append('DPG%s%s%s.XOO' % (org, day.strftime('%y%m%d'), c))
            else:
                names.append('DPG%s%s%s%s.PNO.%s' % (
                    org, day.strftime('%Y%m%d'), c, ('.%s' % lobid) if lobid else '', ext.lower()))
    return names
