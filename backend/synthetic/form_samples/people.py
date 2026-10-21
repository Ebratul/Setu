"""Demo identities for the form samples: five buyers, five suppliers and five orders.

Every name, number and address is invented. Licence, IRC, TIN and USCC values are unique per set
(onboarding refuses a second business with the same licence) and satisfy the real validators in
`app/schemas/onboarding.py`; USCC check characters come from `uscc_check_char`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

D = Decimal


@dataclass(frozen=True, slots=True)
class Buyer:
    n: int
    full_name: str
    designation: str
    mobile: str
    language: str
    legal_name: str
    trade_name: str
    licence_no: str
    authority: str
    expiry: date
    irc_no: str
    tin: str
    division: str
    district: str
    upazila: str
    street: str
    business_type: str
    goods: str
    volume: str
    email: str

    @property
    def address(self) -> str:
        return f"{self.street}, {self.upazila}, {self.district}, {self.division}"


@dataclass(frozen=True, slots=True)
class Supplier:
    n: int
    full_name: str
    designation: str
    mobile: str
    language: str
    legal_en: str
    legal_zh: str
    uscc: str
    province: str
    city: str
    district: str
    street: str
    scope: str
    years: int
    wechat: str
    phone: str
    bank_name: str
    account_no: str
    currency: str
    swift: str
    email: str

    @property
    def address(self) -> str:
        return f"{self.street}, {self.district}, {self.city}, {self.province}"


@dataclass(frozen=True, slots=True)
class Order:
    n: int
    supplier: str  # legal name of a seeded supplier
    supplier_short: str
    title: str
    hs_code: str
    quantity: str
    unit: str
    unit_price: str
    port_of_loading: str
    expected_sale_value: str
    freight: str
    insurance: str
    duty: str
    bank_charges: str
    colour_index: int
    invoice_stem: str  # prefix of document numbers, unique per order

    @property
    def goods_value(self) -> Decimal:
        return D(self.quantity) * D(self.unit_price)


BUYERS: tuple[Buyer, ...] = (
    Buyer(
        1,
        "Rahim Uddin",
        "Managing Director",
        "01712345601",
        "en",
        "Padma Knitwear Ltd",
        "Padma Knit",
        "TRAD/NCC/102345/2026",
        "Narayanganj City Corporation",
        date(2028, 6, 30),
        "BD-IRC-2026-10234",
        "528471936024",
        "Dhaka",
        "Narayanganj",
        "Siddhirganj",
        "Plot 24, BSCIC Industrial Area",
        "MANUFACTURER",
        "Cotton jersey fabric, rib and interlock",
        "2M_10M_BDT",
        "rahim.uddin.demo1@example.com",
    ),
    Buyer(
        2,
        "Nasrin Akter",
        "Director Finance",
        "+8801812345602",
        "bn",
        "Karnaphuli Apparel Sourcing Ltd",
        "KAS Apparel",
        "TRAD/CCC/208871/2026",
        "Chattogram City Corporation",
        date(2028, 12, 31),
        "BD-IRC-2026-20887",
        "614820573119",
        "Chattogram",
        "Chattogram",
        "Panchlaish",
        "House 8, Road 3, Khulshi",
        "TRADER",
        "Polyester woven fabric and linings",
        "500K_2M_BDT",
        "nasrin.akter.demo2@example.com",
    ),
    Buyer(
        3,
        "Tanvir Hasan",
        "Proprietor",
        "01912345603",
        "en",
        "Jamuna Trims & Buttons Trading",
        "Jamuna Trims",
        "TRAD/DNCC/315220/2026",
        "Dhaka North City Corporation",
        date(2029, 3, 31),
        "BD-IRC-2026-31522",
        "703915428",
        "Dhaka",
        "Dhaka",
        "Mirpur",
        "Plot 15, Section 10",
        "TRADER",
        "Buttons, zip fasteners and woven labels",
        "UNDER_500K_BDT",
        "tanvir.hasan.demo3@example.com",
    ),
    Buyer(
        4,
        "Farhana Islam",
        "Chief Executive Officer",
        "+8801512345604",
        "en",
        "Surma Denim Works Ltd",
        "Surma Denim",
        "TRAD/GCC/427761/2026",
        "Gazipur City Corporation",
        date(2029, 9, 30),
        "BD-IRC-2026-42776",
        "8190265470133",
        "Dhaka",
        "Gazipur",
        "Tongi",
        "Konabari Industrial Zone, Block C",
        "MANUFACTURER",
        "Denim fabric and combed cotton yarn",
        "OVER_10M_BDT",
        "farhana.islam.demo4@example.com",
    ),
    Buyer(
        5,
        "Sabbir Ahmed",
        "General Manager",
        "01612345605",
        "bn",
        "Rupsha Home Textiles Ltd",
        "Rupsha Home",
        "TRAD/KCC/539042/2026",
        "Khulna City Corporation",
        date(2028, 3, 31),
        "BD-IRC-2026-53904",
        "9254108763",
        "Khulna",
        "Khulna",
        "Sonadanga",
        "House 21, KDA Avenue",
        "MANUFACTURER",
        "Cotton yarn and fleece fabric",
        "2M_10M_BDT",
        "sabbir.ahmed.demo5@example.com",
    ),
)

SUPPLIERS: tuple[Supplier, ...] = (
    Supplier(
        1,
        "Li Wei",
        "Export Manager",
        "+8613812345611",
        "zh",
        "Hangzhou Yunfeng Textile Co., Ltd.",
        "杭州云丰纺织有限公司",
        "91330106MA2CXK3L7K",
        "Zhejiang",
        "Hangzhou",
        "Xihu",
        "88 Wensan Road",
        "Knitted and woven fabric export",
        9,
        "yunfeng_textile",
        "+86 571 8888 1201",
        "Qiantang River Commercial Bank",
        "6222 0210 0000 1201",
        "USD",
        "QRCXCN2H",
        "li.wei.demo1@example.com",
    ),
    Supplier(
        2,
        "Chen Jing",
        "Sales Director",
        "+8613912345612",
        "zh",
        "Shenzhen Jinlong Garment Accessories Co., Ltd.",
        "深圳金龙服装辅料有限公司",
        "91440300MA5EPR8T40",
        "Guangdong",
        "Shenzhen",
        "Longgang",
        "16 Bantian Industrial Road",
        "Buttons, zip fasteners and labels export",
        12,
        "jinlong_acc",
        "+86 755 8888 1202",
        "Pearl Delta Merchants Bank",
        "6217 0030 0000 1202",
        "CNY",
        "PDMXCN2G",
        "chen.jing.demo2@example.com",
    ),
    Supplier(
        3,
        "Zhang Min",
        "General Manager",
        "+8613712345613",
        "en",
        "Suzhou Hengda Knitting Co., Ltd.",
        "苏州恒达针织有限公司",
        "91320594MA1MQW6H92",
        "Jiangsu",
        "Suzhou",
        "Wuzhong",
        "No. 5 Taihu Avenue",
        "Knitted fabric manufacturing and export",
        6,
        "hengda_knit",
        "+86 512 8888 1203",
        "Taihu Lake Rural Bank",
        "6228 4800 0000 1203",
        "USD",
        "TLRXCN2S",
        "zhang.min.demo3@example.com",
    ),
    Supplier(
        4,
        "Wang Hao",
        "Export Supervisor",
        "+8613612345614",
        "en",
        "Qingdao Rongsheng Yarn Co., Ltd.",
        "青岛荣盛纱线有限公司",
        "91370200MA3C5XN1E5",
        "Shandong",
        "Qingdao",
        "Chengyang",
        "42 Haier Road",
        "Cotton and polyester yarn export",
        15,
        "rongsheng_yarn",
        "+86 532 8888 1204",
        "Jiaozhou Bay Trade Bank",
        "6226 6600 0000 1204",
        "USD",
        "JZBXCN2Q",
        "wang.hao.demo4@example.com",
    ),
    Supplier(
        5,
        "Liu Yang",
        "Foreign Trade Manager",
        "+8613512345615",
        "zh",
        "Shanghai Mingyu Trading Co., Ltd.",
        "上海明宇贸易有限公司",
        "91310115MA1K4HF2QE",
        "Shanghai",
        "Shanghai",
        "Pudong",
        "168 Jinqiao Road",
        "Textile and garment accessories trading",
        4,
        "mingyu_trade",
        "+86 21 8888 1205",
        "Huangpu Commercial Bank",
        "6222 8800 0000 1205",
        "CNY",
        "HPCXCN2S",
        "liu.yang.demo5@example.com",
    ),
)

HUAXIN = "Shaoxing Huaxin Textile Co., Ltd."
BRIGHTLINE = "Ningbo Brightline Accessories Co., Ltd."

ORDERS: tuple[Order, ...] = (
    Order(
        1,
        HUAXIN,
        "Huaxin",
        "Dyed cotton jersey fabric",
        "6006.22",
        "6000",
        "m",
        "1.25",
        "Ningbo",
        "11250.00",
        "520.00",
        "40.00",
        "610.00",
        "95.00",
        0,
        "DJ",
    ),
    Order(
        2,
        HUAXIN,
        "Huaxin",
        "Dyed plain-weave cotton fabric",
        "5208.32",
        "4000",
        "m",
        "1.60",
        "Shanghai",
        "9400.00",
        "430.00",
        "35.00",
        "545.00",
        "80.00",
        1,
        "PW",
    ),
    Order(
        3,
        BRIGHTLINE,
        "Brightline",
        "Metal garment buttons",
        "9606.22",
        "120000",
        "pcs",
        "0.03",
        "Ningbo",
        "5200.00",
        "210.00",
        "20.00",
        "395.00",
        "55.00",
        4,
        "MB",
    ),
    Order(
        4,
        BRIGHTLINE,
        "Brightline",
        "Zip fasteners (nylon coil)",
        "9607.19",
        "30000",
        "pcs",
        "0.18",
        "Ningbo",
        "7800.00",
        "260.00",
        "28.00",
        "570.00",
        "70.00",
        5,
        "ZF",
    ),
    Order(
        5,
        HUAXIN,
        "Huaxin",
        "Dyed polyester woven fabric",
        "5407.52",
        "10000",
        "m",
        "0.85",
        "Shanghai",
        "12600.00",
        "640.00",
        "45.00",
        "700.00",
        "110.00",
        2,
        "PE",
    ),
)
