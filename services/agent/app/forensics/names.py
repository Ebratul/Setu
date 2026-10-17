"""Check codes, the mapping onto the 11 ground-truth names of docs/synthetic-data.md, and labels."""

CHECK_CODES = (
    "QUANTITY_MATCH",
    "VALUE_MATH",
    "VALUE_MATCH",
    "NAME_MATCH",
    "BENEFICIARY_MATCH",
    "VESSEL_VOYAGE_MATCH",
    "DATE_LOGIC",
    "PORT_MATCH",
    "HS_CODE_MATCH",
    "PRICE_BAND",
    "HIDDEN_TEXT",
    "INSTRUCTION_SCAN",
    "METADATA_ANOMALY",
    "DUPLICATE_HASH",
    "PHOTO_MATCH",
    "EXTRACTION_COMPLETE",
    "REFERENCE_CHANGED",
)

# Our check code -> ground-truth check name (None: no ground-truth counterpart).
GROUND_TRUTH: dict[str, str | None] = {
    "QUANTITY_MATCH": "QUANTITY_MATCH",
    "VALUE_MATH": "VALUE_MATCH",
    "VALUE_MATCH": "VALUE_MATCH",
    "VESSEL_VOYAGE_MATCH": "VESSEL_DATE_MATCH",
    "DATE_LOGIC": "VESSEL_DATE_MATCH",
    "NAME_MATCH": "NAME_MATCH",
    "DUPLICATE_HASH": "DUPLICATE_INVOICE",
    "PRICE_BAND": "PRICE_IN_BAND",
    "BENEFICIARY_MATCH": "BENEFICIARY_MATCH",
    "HIDDEN_TEXT": "HIDDEN_TEXT_SCAN",
    "INSTRUCTION_SCAN": "INSTRUCTION_SCAN",
    "PORT_MATCH": "PORT_MATCH",
    "HS_CODE_MATCH": "HS_CODE_MATCH",
    "METADATA_ANOMALY": None,
    "PHOTO_MATCH": None,
    "EXTRACTION_COMPLETE": None,
    "REFERENCE_CHANGED": None,
}
GROUND_TRUTH_NAMES = (
    "QUANTITY_MATCH",
    "VALUE_MATCH",
    "VESSEL_DATE_MATCH",
    "NAME_MATCH",
    "DUPLICATE_INVOICE",
    "PRICE_IN_BAND",
    "BENEFICIARY_MATCH",
    "HIDDEN_TEXT_SCAN",
    "INSTRUCTION_SCAN",
    "PORT_MATCH",
    "HS_CODE_MATCH",
)

# Short, fixed, injection-safe labels (EN, BN) used in explanations, alerts and the chat card.
LABELS: dict[str, tuple[str, str]] = {
    "QUANTITY_MATCH": ("Quantities differ between documents", "ডকুমেন্টগুলোর মধ্যে পরিমাণ মেলেনি"),
    "VALUE_MATH": (
        "Quantity times unit price does not equal the total",
        "পরিমাণ × একক মূল্য মোটের সমান নয়",
    ),
    "VALUE_MATCH": (
        "Price or total differs from the other documents or the deal",
        "দাম বা মোট অন্য ডকুমেন্ট বা ডিলের সাথে মেলেনি",
    ),
    "NAME_MATCH": (
        "Seller name differs from the supplier licence",
        "বিক্রেতার নাম সরবরাহকারীর লাইসেন্সের সাথে মেলেনি",
    ),
    "BENEFICIARY_MATCH": (
        "Bank details differ from the registered account",
        "ব্যাংকের তথ্য নিবন্ধিত অ্যাকাউন্টের সাথে মেলেনি",
    ),
    "VESSEL_VOYAGE_MATCH": (
        "Vessel or voyage differs from the booking",
        "জাহাজ বা ভয়েজ বুকিংয়ের সাথে মেলেনি",
    ),
    "DATE_LOGIC": ("Dates are in an impossible order", "তারিখের ক্রম অসম্ভব"),
    "PORT_MATCH": ("Port or incoterm differs from the deal", "বন্দর বা ইনকোটার্ম ডিলের সাথে মেলেনি"),
    "HS_CODE_MATCH": ("HS code differs from the deal", "এইচএস কোড ডিলের সাথে মেলেনি"),
    "PRICE_BAND": (
        "Unit price is outside the usual band",
        "একক মূল্য স্বাভাবিক সীমার বাইরে",
    ),
    "HIDDEN_TEXT": (
        "The document contains hidden text",
        "ডকুমেন্টে লুকানো লেখা আছে",
    ),
    "INSTRUCTION_SCAN": (
        "The document contains instruction-like text that Setu ignored",
        "ডকুমেন্টে নির্দেশের মতো লেখা আছে, Setu তা উপেক্ষা করেছে",
    ),
    "METADATA_ANOMALY": (
        "File metadata looks edited",
        "ফাইলের মেটাডেটা সম্পাদিত মনে হচ্ছে",
    ),
    "DUPLICATE_HASH": (
        "The same document was already used",
        "একই ডকুমেন্ট আগেই ব্যবহার করা হয়েছে",
    ),
    "PHOTO_MATCH": (
        "Photo does not match the ordered colour",
        "ছবি অর্ডার করা রঙের সাথে মেলেনি",
    ),
    "EXTRACTION_COMPLETE": (
        "Some required fields could not be read or were filled by a model",
        "কিছু প্রয়োজনীয় তথ্য পড়া যায়নি বা মডেল দিয়ে পূরণ করা হয়েছে",
    ),
    "REFERENCE_CHANGED": (
        "Identity, booking, bank details or totals differ from the first accepted proforma invoice",
        "পরিচয়, বুকিং, ব্যাংকের তথ্য বা মোট প্রথম গৃহীত প্রফর্মা ইনভয়েস থেকে আলাদা",
    ),
}

# Neutral check titles for the findings list: they describe WHAT is checked, so they read right
# next to any status (the status says pass, warn or fail). `LABELS` above are the problem
# statements used only when something is wrong (explanations, alerts, chat cards, top reason).
TITLES: dict[str, tuple[str, str]] = {
    "QUANTITY_MATCH": (
        "Quantities match the deal and the other documents",
        "পরিমাণ ডিল ও অন্য ডকুমেন্টের সাথে মেলে",
    ),
    "VALUE_MATH": (
        "Quantity times unit price equals the total",
        "পরিমাণ × একক মূল্য মোটের সমান",
    ),
    "VALUE_MATCH": (
        "Price and total match the deal and the proforma invoice",
        "দাম ও মোট ডিল ও প্রফর্মা ইনভয়েসের সাথে মেলে",
    ),
    "NAME_MATCH": (
        "Seller name matches the supplier licence",
        "বিক্রেতার নাম সরবরাহকারীর লাইসেন্সের সাথে মেলে",
    ),
    "BENEFICIARY_MATCH": (
        "Bank details match the registered account",
        "ব্যাংকের তথ্য নিবন্ধিত অ্যাকাউন্টের সাথে মেলে",
    ),
    "VESSEL_VOYAGE_MATCH": (
        "Vessel and voyage match the booking",
        "জাহাজ ও ভয়েজ বুকিংয়ের সাথে মেলে",
    ),
    "DATE_LOGIC": ("Dates are in a possible order", "তারিখের ক্রম সম্ভব"),
    "PORT_MATCH": ("Ports and incoterm match the deal", "বন্দর ও ইনকোটার্ম ডিলের সাথে মেলে"),
    "HS_CODE_MATCH": ("HS code matches the deal", "এইচএস কোড ডিলের সাথে মেলে"),
    "PRICE_BAND": ("Unit price is within the usual band", "একক মূল্য স্বাভাবিক সীমার মধ্যে"),
    "HIDDEN_TEXT": ("Document has no hidden text", "ডকুমেন্টে কোনো লুকানো লেখা নেই"),
    "INSTRUCTION_SCAN": (
        "Document has no instruction-like text",
        "ডকুমেন্টে নির্দেশের মতো কোনো লেখা নেই",
    ),
    "METADATA_ANOMALY": ("File metadata looks unedited", "ফাইলের মেটাডেটা অসম্পাদিত মনে হয়"),
    "DUPLICATE_HASH": ("Document is not a duplicate", "ডকুমেন্টটি অন্য কোনো ডকুমেন্টের প্রতিলিপি নয়"),
    "PHOTO_MATCH": ("Photo colour matches the order", "ছবির রং অর্ডারের সাথে মেলে"),
    "EXTRACTION_COMPLETE": (
        "All required fields were read from the file",
        "সব প্রয়োজনীয় তথ্য ফাইল থেকে পড়া গেছে",
    ),
    "REFERENCE_CHANGED": (
        "Invoice matches the pinned proforma invoice",
        "ইনভয়েস নির্ধারিত প্রফর্মা ইনভয়েসের সাথে মেলে",
    ),
}
