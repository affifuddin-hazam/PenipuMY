def parse_duitnow_qr(payload: str) -> dict:
    """
    Extract ONLY important info from DuitNow QR:
    - Merchant Name
    - Identifier (Account / Phone / Security ID)
    - Bank Name
    """

    # Mapping minimum bank/acquirer code → bank name
    BANK_CODE_MAP = {
        "629295": "AEON Bank (M) Berhad",
        "501664": "Affin Bank Berhad",
        "432134": "Al Rajhi Banking & Investment Corporation (Malaysia) Berhad",
        "504374": "Alliance Bank Malaysia Berhad",
        "564169": "AmBank Malaysia Berhad",
        "890293": "Ampersand Pay Sdn Bhd",
        "890061": "Axiata Digital eCode Sdn Bhd",
        "603346": "Bank Islam Malaysia Berhad",
        "589267": "Bank Kerjasama Rakyat Malaysia Berhad",
        "564167": "Bank Muamalat Malaysia Berhad",
        "629188": "Bank of America (M) Berhad",
        "629152": "Bank of China (M) Berhad",
        "589373": "Bank Pertanian Malaysia Berhad (Agrobank)",
        "420709": "Bank Simpanan Nasional",
        "890236": "Beez Fintech Sdn Bhd",
        "890012": "BigPay Malaysia Sdn Bhd",
        "629204": "BNP Paribas Malaysia Berhad",
        "629303": "Boost Bank Berhad",
        "890244": "Boost Connect Sdn Bhd",
        "629261": "China Construction Bank (Malaysia) Berhad",
        "501854": "CIMB Bank Berhad",
        "589170": "Citibank Berhad",
        "890160": "Curlec Sdn Bhd",
        "629246": "Deutsche Bank (M) Berhad",
        "890145": "Fass Payment Solutions Sdn Bhd",
        "890020": "Fave Asia Technologies Sdn Bhd",
        "890038": "Finexus Cards Sdn Bhd",
        "890103": "GHL Cardpay Sdn Bhd",
        "890186": "Global Payments Asia-Pacific Limited",
        "890046": "GPay Network (M) Sdn Bhd (GrabPay)",
        "629279": "GX Bank Berhad",
        "588830": "Hong Leong Bank Berhad",
        "589836": "HSBC Bank Berhad",
        "629253": "Industrial and Commercial Bank of China (M) Berhad",
        "890178": "Instapay Technologies Sdn Bhd",
        "890079": "iPay88 (M) Sdn Bhd",
        "629212": "JP Morgan Chase Bank Berhad",
        "629311": "KAF Investment Bank Berhad",
        "890152": "Kiplepay Sdn Bhd",
        "890228": "Koperasi Co-opbank Pertama Malaysia Berhad",
        "639406": "Kuwait Finance House (Malaysia) Berhad",
        "588734": "Malayan Banking Berhad (Maybank)",
        "890301": "ManagePay Systems Sdn Bhd",
        "432310": "MBSB Bank Berhad",
        "890111": "Merchantrade Asia Sdn Bhd",
        "629220": "Mizuho Bank (Malaysia) Berhad",
        "890210": "MobilityOne Sdn Bhd",
        "890277": "Mobiedge E-commerce Sdn Bhd",
        "890327": "MRuncit Commerce Sdn Bhd",
        "629196": "MUFG Bank (Malaysia) Berhad",
        "504324": "OCBC Bank Berhad",
        "890269": "Paydibs Sdn Bhd",
        "890194": "Payex PLT",
        "564162": "Public Bank Berhad",
        "890087": "Razer Merchant Services Sdn Bhd",
        "890095": "Revenue Solution Sdn Bhd",
        "564160": "RHB Bank Berhad",
        "890129": "Setel Ventures Sdn Bhd",
        "890004": "ShopeePay Malaysia Sdn Bhd",
        "890202": "SiliconNet Technologies Sdn Bhd",
        "539981": "Standard Chartered Bank Malaysia Berhad",
        "890137": "Stripe Payments Singapore Pte Ltd",
        "629238": "Sumitomo Mitsui Banking Corporation (M) Berhad",
        "890053": "TNG Digital Sdn Bhd",
        "890251": "UniPin (M) Sdn Bhd",
        "519469": "United Overseas Bank (Malaysia) Berhad",
        "890319": "Wannapay Sdn Bhd",
        "629287": "YTL Digital Bank Berhad",
        "890285": "2C2P System Sdn Bhd",
        "898989": "JomPAY"
    }


    result = {
        "merchant_name": None,
        "identifier": None,
        "bank_name": None
    }

    i = 0
    while i + 4 <= len(payload):
        tag = payload[i:i+2]
        length = int(payload[i+2:i+4])
        value = payload[i+4:i+4+length]

        # 1️. Merchant Name
        if tag == "59":
            result["merchant_name"] = value.strip()

        # 2️. Merchant Account Information (26–51)
        if tag.isdigit() and 26 <= int(tag) <= 51:
            j = 0
            while j + 4 <= len(value):
                sub_tag = value[j:j+2]
                sub_len = int(value[j+2:j+4])
                sub_val = value[j+4:j+4+sub_len]

                # Identifier (account / phone / security ID)
                if sub_tag == "02" and not result["identifier"]:
                    result["identifier"] = sub_val.strip()

                # Bank / Acquirer code
                if sub_tag == "01" and not result["bank_name"]:
                    result["bank_name"] = BANK_CODE_MAP.get(sub_val, f"Unknown Bank Code {sub_val}")

                j += 4 + sub_len

        i += 4 + length

    return result
