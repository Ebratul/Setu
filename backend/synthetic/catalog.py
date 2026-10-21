"""Fictional master data: goods and price bands, counterparties, ports, banks, vessels.

Every name is invented. Bank codes use an `X` as the fourth letter and account numbers start
with `SIM-`, so none of them can be a real identifier. Price bands and duty rates are
illustrative only.
"""

from dataclasses import dataclass
from decimal import Decimal

D = Decimal


@dataclass(frozen=True, slots=True)
class Goods:
    hs: str
    kind: str  # fabric | yarn | accessory
    name: str
    unit: str
    band: tuple[Decimal, Decimal]  # plausible unit price, USD per unit
    price_dp: int
    kg_per_unit: Decimal
    pkg_type: str
    per_pkg: tuple[int, ...]
    tare_kg: Decimal  # packaging weight per package
    qty_range: tuple[int, int]
    qty_step: int
    duty_rate: Decimal  # illustrative effective duty on assessed value
    widths_cm: tuple[int, ...] = ()
    gsm: tuple[int, ...] = ()
    counts: tuple[str, ...] = ()
    sizes: tuple[str, ...] = ()


GOODS: tuple[Goods, ...] = (
    Goods(
        "6006.22",
        "fabric",
        "Dyed cotton jersey fabric",
        "m",
        (D("0.95"), D("1.65")),
        2,
        D("0.27"),
        "ROLLS",
        (80, 100, 120),
        D("1.20"),
        (3000, 40000),
        100,
        D("0.078"),
        widths_cm=(150, 160, 180),
        gsm=(160, 180, 200),
    ),
    Goods(
        "5407.52",
        "fabric",
        "Dyed polyester woven fabric",
        "m",
        (D("0.60"), D("1.30")),
        2,
        D("0.14"),
        "ROLLS",
        (100, 150),
        D("1.00"),
        (5000, 60000),
        100,
        D("0.082"),
        widths_cm=(145, 150),
        gsm=(75, 90, 110),
    ),
    Goods(
        "5208.32",
        "fabric",
        "Dyed plain-weave cotton fabric",
        "m",
        (D("1.10"), D("2.10")),
        2,
        D("0.19"),
        "ROLLS",
        (60, 80, 100),
        D("1.10"),
        (3000, 30000),
        100,
        D("0.085"),
        widths_cm=(140, 150),
        gsm=(130, 150, 170),
    ),
    Goods(
        "5509.21",
        "yarn",
        "Polyester staple fibre yarn",
        "kg",
        (D("1.35"), D("2.30")),
        2,
        D("1"),
        "BAGS",
        (25, 50),
        D("0.40"),
        (2000, 20000),
        50,
        D("0.060"),
        counts=("Ne 30/1", "Ne 40/1", "Ne 20/1"),
    ),
    Goods(
        "5205.22",
        "yarn",
        "Combed cotton yarn",
        "kg",
        (D("2.80"), D("4.40")),
        2,
        D("1"),
        "CARTONS",
        (20, 25),
        D("0.50"),
        (2000, 15000),
        50,
        D("0.055"),
        counts=("Ne 30/1", "Ne 40/1", "Ne 50/1"),
    ),
    Goods(
        "5402.33",
        "yarn",
        "Textured polyester filament yarn",
        "kg",
        (D("1.40"), D("2.40")),
        2,
        D("1"),
        "CARTONS",
        (20, 24),
        D("0.50"),
        (2000, 18000),
        50,
        D("0.058"),
        counts=("150D/48F", "300D/96F", "75D/36F"),
    ),
    Goods(
        "9606.22",
        "accessory",
        "Metal garment buttons",
        "pcs",
        (D("0.015"), D("0.045")),
        3,
        D("0.004"),
        "CARTONS",
        (5000, 10000),
        D("0.80"),
        (50000, 600000),
        1000,
        D("0.110"),
        sizes=("18L", "24L", "30L"),
    ),
    Goods(
        "9607.19",
        "accessory",
        "Zip fasteners (nylon coil)",
        "pcs",
        (D("0.10"), D("0.30")),
        2,
        D("0.012"),
        "CARTONS",
        (1000, 2000),
        D("0.80"),
        (10000, 150000),
        500,
        D("0.105"),
        sizes=("#3 55 cm", "#5 70 cm", "#5 20 cm"),
    ),
)
GOODS_BY_HS = {g.hs: g for g in GOODS}

COLOURS: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("Navy Blue", (24, 43, 87)),
    ("Maroon", (110, 25, 38)),
    ("Forest Green", (34, 85, 52)),
    ("Charcoal Grey", (66, 69, 73)),
    ("Royal Blue", (36, 70, 160)),
    ("Black", (22, 22, 24)),
    ("Off White", (232, 228, 214)),
    ("Olive", (106, 112, 52)),
    ("Mustard", (200, 154, 36)),
    ("Teal", (30, 120, 124)),
    ("Burgundy", (96, 20, 48)),
    ("Sky Blue", (126, 176, 218)),
)

# ---- counterparties -------------------------------------------------------------------------
SUPPLIER_CITIES: tuple[tuple[str, str], ...] = (
    ("Shaoxing", "Zhejiang"),
    ("Ningbo", "Zhejiang"),
    ("Guangzhou", "Guangdong"),
    ("Keqiao", "Zhejiang"),
)
# invented brand words; the demo suppliers' words (Huaxin, Brightline, Huameng) are left out
SUPPLIER_BRANDS = (
    "Yunfeng",
    "Zhongtai",
    "Jinlong",
    "Hengda",
    "Rongsheng",
    "Mingyu",
    "Tianyi",
    "Xinhe",
    "Boyuan",
    "Lixin",
    "Dasheng",
    "Qianhe",
    "Fuyuan",
    "Ruitai",
    "Shengbao",
    "Taihe",
)
SUPPLIER_PRODUCT_WORDS = {
    "fabric": ("Textile", "Fabrics", "Knitting"),
    "yarn": ("Yarn", "Spinning", "Textile"),
    "accessory": ("Accessories", "Trimmings", "Garment Accessories"),
}
SUPPLIER_STREETS = (
    "Jiangnan Road",
    "Binhai Avenue",
    "Zhongshan Road",
    "Textile Park Road",
    "Xingye Road",
    "Hexi Street",
)

BUYER_WORDS = (
    "Noor",
    "Sagor",
    "Tuli",
    "Anika",
    "Sultana",
    "Rupali",
    "Kazi",
    "Mitu",
    "Shapna",
    "Alif",
    "Bijoy",
    "Orna",
)
BUYER_SUFFIXES = (
    "Knitwear Ltd.",
    "Apparels Ltd.",
    "Garments Ltd.",
    "Textiles Ltd.",
    "Fashion Wear",
)
BUYER_CITIES: tuple[tuple[str, str], ...] = (
    ("Narayanganj", "BSCIC Industrial Area, Narayanganj-1400"),
    ("Gazipur", "Konabari Industrial Zone, Gazipur-1700"),
    ("Dhaka", "Mirpur Section 10, Dhaka-1216"),
)
TRADE_LICENCE_PREFIX = {"Narayanganj": "NCC", "Gazipur": "GCC", "Dhaka": "DNCC"}

# ---- ports and logistics --------------------------------------------------------------------
PORTS_OF_LOADING = ("Ningbo", "Shanghai", "Shenzhen")
PORT_OF_DISCHARGE = "Chittagong"
WRONG_PORTS = ("Colombo", "Port Klang", "Singapore", "Mongla", "Kolkata", "Busan")
PORT_CODES = {"Ningbo": "NGB", "Shanghai": "SHA", "Shenzhen": "SZX", "Chittagong": "CGP"}
TRANSIT_DAYS = (14, 24)  # on-board to arrival, days
MIN_TRANSIT_DAYS = 7  # validator floor; anything shorter is not physically plausible

CARRIERS = (
    ("Kelmar Container Line", "KMCL", "KMCU"),
    ("Tamra Ocean Lines", "TMOL", "TMOU"),
    ("Orienta Shipping Co.", "ORSH", "ORSU"),
)
VESSEL_PREFIXES = ("KELMAR", "TAMRA", "ORIENTA", "VANTARA", "SORELL", "NAVARA")
VESSEL_NOUNS = (
    "PEARL",
    "HARMONY",
    "TRADER",
    "PIONEER",
    "LOTUS",
    "SPIRIT",
    "ARROW",
    "DELTA",
    "BREEZE",
    "VOYAGER",
)

# ---- banks ----------------------------------------------------------------------------------
CN_BANKS = (
    ("Shaoxing Riverside Commercial Bank", "SRBX", "CN", "2S"),
    ("Ningbo Harbour Bank", "NHBX", "CN", "2N"),
    ("Pearl River Merchants Bank", "PRMX", "CN", "2G"),
    ("Keqiao Rural Credit Bank", "KRCX", "CN", "2K"),
    ("Yangtze Trade Bank", "YTBX", "CN", "2S"),
)
HK_BANKS = (
    ("Victoria Harbour Trade Bank", "VHTX", "HK", "HH"),
    ("Kowloon Pacific Bank", "KPBX", "HK", "HH"),
    ("Peninsula Mercantile Bank", "PMBX", "HK", "HH"),
)
PERSONAL_NAMES = ("Li Na", "Wang Fang", "Zhang Lei", "Liu Yang", "Zhao Min", "Sun Hao")
FOREIGN_FX_RATE_USD_BDT = D("122.59")  # same mock rate as the seed

ISSUING_BODY = "Zhejiang Council for Trade Promotion (simulated)"
FOOTER = "SIMULATED – FOR TESTING"
