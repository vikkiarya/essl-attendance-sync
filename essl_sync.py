import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
from xml.sax.saxutils import escape

# ============================================================
# SETTINGS
# ============================================================

ESSL_URL = "http://157.20.196.180:8192/iclock/WebAPIService.asmx"

API_USER = "api"
API_PASSWORD = "xxxxx"   # APNA ACTUAL API PASSWORD

DEVICES = [
    "NCD8250201389",
    "NCD8235300629"
]

# April 2026 se data
FROM_DATE = "2026-04-01 00:00:00"

# Aaj tak
TO_DATE = datetime.now().strftime("%Y-%m-%d 23:59:59")


# ============================================================
# GOOGLE APPS SCRIPT WEB APP
# ============================================================

GOOGLE_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbybslHgvySJ7ZmQ55GHlyQTHE5T9SgUtjqc4b8pp0kO47RI-fzQdkh6xUbchg6-JQel"
    "/exec"
)

SECRET_TOKEN = "ESSL-2026-TEST-12345"


# ============================================================
# GET TRANSACTIONS FROM ESSL
# ============================================================

def get_transactions(serial):

    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">

    <soap:Body>

        <GetTransactionsLog xmlns="http://tempuri.org/">

            <FromDateTime>{escape(FROM_DATE)}</FromDateTime>

            <ToDateTime>{escape(TO_DATE)}</ToDateTime>

            <SerialNumber>{escape(serial)}</SerialNumber>

            <UserName>{escape(API_USER)}</UserName>

            <UserPassword>{escape(API_PASSWORD)}</UserPassword>

            <strDataList></strDataList>

        </GetTransactionsLog>

    </soap:Body>

</soap:Envelope>
"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": '"http://tempuri.org/GetTransactionsLog"'
    }

    try:

        response = requests.post(
            ESSL_URL,
            data=soap_body.encode("utf-8"),
            headers=headers,
            timeout=180
        )

    except Exception as e:

        print(f"ERROR connecting to device {serial}:")
        print(e)

        return ""


    print(
        f"Device {serial} | "
        f"HTTP {response.status_code} | "
        f"Length {len(response.text)}"
    )


    if response.status_code != 200:

        print("eSSL ERROR RESPONSE:")
        print(response.text[:3000])

        return ""


    # ========================================================
    # PARSE SOAP XML
    # ========================================================

    try:

        root = ET.fromstring(response.content)

    except Exception as e:

        print("XML PARSE ERROR:", e)
        print(response.text[:3000])

        return ""


    result_text = ""
    data_list_text = ""


    for element in root.iter():

        tag = element.tag.split("}")[-1]


        if tag == "GetTransactionsLogResult":

            result_text = element.text or ""


        elif tag == "strDataList":

            data_list_text = element.text or ""


    # ========================================================
    # IMPORTANT
    # Actual punches are in strDataList
    # GetTransactionsLogResult only gives Logs Count
    # ========================================================

    result_text = result_text.strip()

    raw = data_list_text.strip()


    print("Logs result:", result_text)

    print(
        "Actual punch data length:",
        len(raw)
    )


    return raw


# ============================================================
# PARSE RAW PUNCH DATA
# ============================================================

def parse_transactions(raw):

    records = []


    if not raw:

        return records


    for line in raw.splitlines():

        line = line.strip()


        if not line:

            continue


        # eSSL format:
        # EmployeeCode<TAB>DateTime<TAB>

        parts = line.split("\t")


        if len(parts) < 2:

            continue


        emp_code = parts[0].strip()

        punch_time = parts[1].strip()


        if not emp_code:

            continue


        try:

            dt = datetime.strptime(
                punch_time,
                "%Y-%m-%d %H:%M:%S"
            )

        except ValueError:

            continue


        records.append(
            (
                emp_code,
                dt
            )
        )


    return records


# ============================================================
# CREATE DAILY ATTENDANCE
# ============================================================

def make_daily_rows(records):

    grouped = defaultdict(list)


    # Employee + Date wise grouping

    for emp_code, dt in records:

        key = (
            emp_code,
            dt.strftime("%Y-%m-%d")
        )

        grouped[key].append(dt)


    rows = []


    for (emp_code, date), punches in grouped.items():

        punches.sort()


        # First punch = IN

        first_punch = punches[0]


        # Last punch = OUT

        last_punch = punches[-1]


        # Only one punch

        if first_punch == last_punch:

            out_time = ""

            total_working = 0


        else:

            out_time = last_punch.strftime(
                "%H:%M:%S"
            )


            seconds = (
                last_punch - first_punch
            ).total_seconds()


            # TRUE decimal hours
            # 9 hours 30 minutes = 9.5

            total_working = round(
                seconds / 3600,
                2
            )


        rows.append({

            "emp_code": emp_code,

            "date": date,

            "in_time": first_punch.strftime(
                "%H:%M:%S"
            ),

            "out_time": out_time,

            "total_working": total_working

        })


    # Date + Employee Code sorting

    rows.sort(
        key=lambda x: (
            x["date"],
            x["emp_code"]
        )
    )


    return rows


# ============================================================
# SEND DATA TO GOOGLE SHEETS
# ============================================================

def send_to_google(rows):

    payload = {

        "token": SECRET_TOKEN,

        "rows": rows

    }


    try:

        response = requests.post(

            GOOGLE_URL,

            json=payload,

            timeout=300

        )

    except Exception as e:

        print("GOOGLE CONNECTION ERROR:")

        print(e)

        return False


    print(
        "Google HTTP:",
        response.status_code
    )


    print(
        response.text[:5000]
    )


    if response.status_code != 200:

        return False


    return True


# ============================================================
# MAIN
# ============================================================

print("=" * 60)

print(
    "eSSL → GOOGLE SHEETS ATTENDANCE SYNC"
)

print("=" * 60)


print(
    "FROM:",
    FROM_DATE
)


print(
    "TO  :",
    TO_DATE
)


print(
    "USER:",
    API_USER
)


print()


# ============================================================
# GET ALL DEVICE RECORDS
# ============================================================

all_records = []


for device in DEVICES:

    print(
        "------------------------------------------------------------"
    )

    raw = get_transactions(device)


    records = parse_transactions(raw)


    print(
        f"Records from {device}: {len(records)}"
    )


    # Show first 3 records for verification

    if records:

        print("Sample records:")

        for sample in records[:3]:

            print(
                sample[0],
                sample[1]
            )


    all_records.extend(records)


# ============================================================
# TOTAL RAW PUNCHES
# ============================================================

print()

print(
    "TOTAL RAW PUNCHES:",
    len(all_records)
)


# ============================================================
# DAILY ATTENDANCE
# ============================================================

daily_rows = make_daily_rows(
    all_records
)


print(
    "DAILY ATTENDANCE ROWS:",
    len(daily_rows)
)


# ============================================================
# SEND TO GOOGLE
# ============================================================

print()

print(
    "Sending to Google Sheets..."
)


success = send_to_google(
    daily_rows
)


print()

print("=" * 60)


if success:

    print(
        "SYNC COMPLETE"
    )

else:

    print(
        "SYNC FAILED"
    )


print("=" * 60)