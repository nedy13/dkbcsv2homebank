#!/usr/bin/env python3

# http://homebank.free.fr/help/06csvformat.html
import os
from decimal import Decimal
from datetime import datetime
import glob

PAYMODES = ["None",  # 0
            "Credit Card",  # 1
            "Check",  # 2
            "Cash",  # 3
            "Transfer",  # 4
            "Internal Transfer",  # 5
            "Debit Card",  # 6
            "Standing Order",  # 7
            "Electronic Payment",  # 8
            "Deposit",  # 9
            "FI Fees"]  # 10
PAYMODE_NONE = 0
PAYMODE_CREDIT_CARD = 1
PAYMODE_CASH = 3
PAYMODE_INTERNAL_TRANSFER = 5
PAYMODE_EINZUG = 8
PAYMODE_FEE = 10

OUTPUT_FOLDER = "output_data"


def split_line(line):
    """returns a list csv elements"""
    # it removes semicolons from the end of the line first
    # print("%r" % line.strip(";").split(";"))
    return list(map(lambda x: x.strip('"'), line.strip(";\n").split(";")))


def get_data(line, assert_type=None, convert=lambda x: x):
    csv_type, value = split_line(line)
    if assert_type:
        assert csv_type == assert_type
    return convert(value)


def to_string(value):
    return value


def to_decimal(value):
    if " " in value:
        value, _ = value.split(" ", 1)
    # values greater than 1000 have a thousand separator e.g. 1.250,34
    if "." in value:
        value = value.replace(".", "")
    return Decimal(value.replace(",", "."))


def to_date(value):
    return datetime.strptime(value, "%d.%m.%Y")


def get_string_until(astr, break_chars=" 123456780,;.-", valid_char=lambda x: True):
    ret = []
    for char in astr:
        if valid_char(char) and char not in break_chars:
            ret.append(char)
        else:
            break
    return "".join(ret)


def guess_paymode(payee, description, default=PAYMODE_NONE):
    if payee in ("HVB", "STADTSPARKASSE", "AUSZAHLUNG", "Einzahlung"):
        return PAYMODE_INTERNAL_TRANSFER
    if payee == "DKB":
        return PAYMODE_FEE
    return default


def guess_payee(description):
    name = get_string_until(description)
    if name == "":
        return "DKB"

    return name.upper()


def guess_category(payee, description, last_catergory=""):
    if payee == "WEBFACTION":
        return "Homepage:webfaction"
    if payee == "GH":
        return "Homepage:github"
    elif payee == "DB":
        return "Travel:Train"
    elif payee == "GOOGLE":
        if "Music" in description:
            return "Multimedia:Music"
    elif payee == "HABENZINSENZ":
        return "Vermögenseinkommen:Zinsen"
    elif payee == "DKB":
        if "für Auslandseinsatz" in description:
            return last_catergory or "Transaction Fee"
    elif "HUMBLE" in payee:
        return "hobby:games"
    return ""


def convert_csv(csv_filename):
    csv_fh = open(csv_filename, encoding="latin-1")
    account_type, account_info = split_line(csv_fh.readline())
    if account_type == "Kreditkarte:":
        it = get_transactions_visadkb(csv_fh)
        von, bis = next(it)
        fn = OUTPUT_FOLDER + os.path.sep + "dkbvisa_%s-%s_%s.csv" % (account_info[:4], von.strftime("%y%m%d"), bis.strftime("%y%m%d"))
        with open(fn, "w") as fh:
            # fh.write(Transaction.csv_head)
            for transaction in it:
                fh.write(transaction.to_csv())
    elif account_type == "Kontonummer:":
        it = get_transactions_girodkb(csv_fh)
        von, bis = next(it)
        fn = OUTPUT_FOLDER + os.path.sep + "dkbgiro_%s-%s_%s.csv" % (account_info[:22], von.strftime("%y%m%d"), bis.strftime("%y%m%d"))
        with open(fn, "w") as fh:
            # fh.write(Transaction.csv_head)
            for transaction in it:
                fh.write(transaction.to_csv())
    else:
        print("Unknown Accounttype")


def convert_folder(input_csv_folder):
    csv_files = glob.glob(input_csv_folder + os.path.sep + "*.csv", recursive=True)
    if not os.path.isdir(OUTPUT_FOLDER):
        os.mkdir(OUTPUT_FOLDER)
    for csv in csv_files:
        convert_csv(csv)


class Transaction(object):
    csv_head = "date;paymode;info;payee;description;amount;category;tags\n"

    def __init__(self, date, amount, **kw):
        # date ; paymode ; info ; payee ; description ; amount ; category
        self.date = date
        self.paymode = kw.get('paymode', PAYMODE_NONE)
        self.info = kw.get('info', "")
        self.payee = kw.get('payee', "Unknown")
        self.description = kw.get('description', "")
        self.amount = amount
        self.category = kw.get('category', "")
        self.tags = kw.get('tags', "")

    def get_csv_date(self):
        return self.date.strftime("%d-%m-%y")

    def get_csv_paymode(self):
        return str(self.paymode)

    def get_csv_info(self):
        return self.info

    def get_csv_payee(self):
        return self.payee

    def get_csv_description(self):
        return self.description

    def get_csv_amount(self):
        return "%.2f" % self.amount

    def get_csv_category(self):
        return self.category

    def get_csv_tags(self):
        return self.tags

    def to_csv(self):
        data = ["date", "paymode", "info", "payee", "description", "amount", "category", "tags"]
        return "%s\n" % ";".join(map(lambda x: getattr(self, "get_csv_%s" % x)(), data))


# 1 "Kreditkarte:";"4998************ Kreditkarte";
# 2
# 3 "Von:";"27.12.2012";
# 4 "Bis:";"04.01.2013";
# 5 "Saldo:";"11266.89 EUR";
# 6 "Datum:";"04.01.2013";
# 7 
# 8 "Umsatz abgerechnet";"Wertstellung";"Belegdatum";"Beschreibung";"Betrag (EUR)";"Ursprünglicher Betrag";;
# 9 "Nein";"04.01.2013";"03.01.2013";"Amazon EUAMAZON.DE";"-27,77";"";
VISA_DESC = '"Umsatz abgerechnet";"Wertstellung";"Belegdatum";"Beschreibung";"Betrag (EUR)";"Ursprünglicher Betrag";\n'


def get_transactions_visadkb(csv_fh):
    assert csv_fh.readline() == '\n'
    von = get_data(csv_fh.readline(), assert_type="Von:", convert=to_date)
    bis = get_data(csv_fh.readline(), assert_type="Bis:", convert=to_date)
    saldo = get_data(csv_fh.readline(), assert_type="Saldo:")
    datum = get_data(csv_fh.readline(), assert_type="Datum:")
    assert csv_fh.readline() == '\n'
    visa_desc = csv_fh.readline()
    assert visa_desc == VISA_DESC, "\n%r\n%r" % (visa_desc, VISA_DESC)

    yield (von, bis)
    last_catergory = ""
    for line in csv_fh:
        wertstellung, beschreibung, betrag = get_dkbvisa_transaction(line)
        payee = guess_payee(beschreibung)
        category = guess_category(payee, beschreibung, last_catergory=last_catergory)
        paymode = guess_paymode(payee, beschreibung, default=PAYMODE_CREDIT_CARD)
        t = Transaction(date=wertstellung, amount=betrag, description=beschreibung,
                        payee=payee, category=category, paymode=paymode, tags="")
        yield t
        # print(t.to_csv())


def get_dkbvisa_transaction(line):
    convert_l = [to_date, to_string, to_decimal]
    _, wertstellung, _, beschreibung, betrag, urspruenglich = split_line(line)
    if urspruenglich:
        beschreibung += " ursprünglich %s" % urspruenglich
    return list(map(lambda x: x[0](x[1]), zip(convert_l, [wertstellung, beschreibung, betrag])))


# 1 "Kontonummer:";"12774055 / Internet-Konto";
# 2
# 3 "Von:";"27.12.2012";
# 4 "Bis:";"04.01.2013";
# 5 "Kontostand vom:";"500,00";
# 6
# 7 "Buchungstag";"Wertstellung";"Buchungstext";"Auftraggeber/Begünstigter";"Verwendungszweck";"Kontonummer";"BLZ";"Betrag (EUR)";
# 7a "Buchungstag";"Wertstellung";"Buchungstext";"Auftraggeber / Begünstigter";"Verwendungszweck";"Kontonummer";"BLZ";"Betrag (EUR)";"Gläubiger-ID";"Mandatsreferenz";"Kundenreferenz";
# 8 "04.01.2013";"04.01.2013";"LASTSCHRIFT";"AZ REAL ESTATE GERMANY";"X X 01.01.13-31.01.13-GM WOHNEN 01.01.13-31.01.13-VZ BK 01.01.13-31.01.13-VZ HK X ";"905001200";"60080000";"-1.091,00";
# 8a "18.03.2016";"19.03.2016";"Kartenzahlung/-abrechnung";"RAIFFEISEN-WARENGENOSSENSCHAFT//JAMELN/DE / Raiff-Wa-Ge eG Jameln";"2016-03-17T11:32:01 Karte0 2018-12";"DE01234567890456776651";"GENODEF3PER";"-22,82";"";"";"75036123456789234566787665";

GIRO_DESC = '"Buchungstag";"Wertstellung";"Buchungstext";"Auftraggeber / Begünstigter";"Verwendungszweck";"Kontonummer";"BLZ";"Betrag (EUR)";"Gläubiger-ID";"Mandatsreferenz";"Kundenreferenz";\n'


def get_transactions_girodkb(csv_fh):
    assert csv_fh.readline() == '\n'
    von = get_data(csv_fh.readline(), assert_type="Von:", convert=to_date)
    bis = get_data(csv_fh.readline(), assert_type="Bis:", convert=to_date)
    saldo = get_data(csv_fh.readline(), assert_type="Kontostand vom:")
    assert csv_fh.readline() == '\n'
    giro_desc = csv_fh.readline()
    assert giro_desc == GIRO_DESC, "\n%r\n%r" % (giro_desc, VISA_DESC)

    yield (von, bis)
    last_catergory = ""
    for line in csv_fh:
        wertstellung, payee, beschreibung, betrag = get_dkbgiro_transaction(line)
        # payee = guess_payee(beschreibung)
        payee = payee.upper()
        category = guess_category(payee, beschreibung, last_catergory=last_catergory)
        paymode = guess_paymode(payee, beschreibung, default=PAYMODE_CREDIT_CARD)
        t = Transaction(date=wertstellung, amount=betrag, description=beschreibung,
                        payee=payee, category=category, paymode=paymode, tags="")
        yield t
        # print(t.to_csv())


def get_dkbgiro_transaction(line):
    convert_l = [to_date, to_string, to_string, to_decimal]
    _, wertstellung, _, auftraggeber, verwendungszweck, _, _, betrag, _, _, _ = split_line(line)
    return list(map(lambda x: x[0](x[1]), zip(convert_l, [wertstellung, auftraggeber, verwendungszweck, betrag])))


# Column list (OUTPUT file):
#         date ; paymode ; info ; payee ; description ; amount ; category ; tags

#         Values:
#         date     => format should be DD-MM-YY
#         mode     => from 0=none to 10=FI fee
#         info     => a string
#         payee    => a payee name
#         description  => a string
#         amount   => a number with a '.' as decimal separator, ex: -24.12 or 36.75
#         category => a full category name (category, or category:subcategory)
#         tags => tags separated by space tag is mandatory since v4.5


if __name__ == "__main__":
    convert_folder("input_data")
