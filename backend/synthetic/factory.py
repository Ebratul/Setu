"""Builds consistent packs from a `Plan` (random from a seed, or the fixed demo plan)."""

import math
import random
import string
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from synthetic import catalog as cat
from synthetic.models import (
    BankDetails,
    BillOfEntryDoc,
    BillOfLadingDoc,
    CertOfOriginDoc,
    DealTerms,
    InvoiceDoc,
    Pack,
    PackingListDoc,
    Party,
    PhotoDoc,
    RenderStyle,
    Schedule,
)

D = Decimal
CENT = D("0.01")
DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%B %d, %Y")
PAYMENT_TERMS = (
    "30% advance at production start, 60% against B/L copy, 10% on arrival "
    "(milestone escrow, simulated)",
    "T/T: 30% deposit, 60% before shipment, 10% after arrival (milestone escrow, simulated)",
)


def rng_for(seed: int, stream: str) -> random.Random:
    """Seeded RNG per named stream; str seeds are hashed, so this is stable across processes."""
    return random.Random(f"setu-synth-v1:{seed}:{stream}")


def q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def mask_account(number: str) -> str:
    parts = number.split("-")
    parts[-2] = "****"
    return "-".join(parts)


def iso6346_check_digit(code10: str) -> int:
    values: dict[str, int] = {}
    n = 10
    for ch in string.ascii_uppercase:
        if n % 11 == 0:
            n += 1
        values[ch] = n
        n += 1
    total = sum((values[c] if c.isalpha() else int(c)) * 2**i for i, c in enumerate(code10))
    return total % 11 % 10


def container_number(prefix: str, serial: int) -> str:
    body = f"{prefix}{serial % 1_000_000:06d}"
    return f"{body}{iso6346_check_digit(body)}"


def scramble(index: int) -> int:
    """Bijective on 0..8999, so invoice numbers never collide across packs."""
    return (index * 7919 + 1301) % 9000 + 1000


@dataclass(frozen=True, slots=True)
class Supplier:
    party: Party
    city: str
    kind: str
    bank: BankDetails


@dataclass(frozen=True, slots=True)
class Plan:
    index: int
    order_ref: str
    supplier: Supplier
    buyer: Party
    goods: cat.Goods
    colour: tuple[str, tuple[int, int, int]]
    description: str
    width_cm: int | None
    quantity: Decimal
    unit_price: Decimal
    per_pkg: int
    pol: str
    incoterm: str
    carrier: tuple[str, str, str]
    vessel: str
    voyage: str
    bl_no: str
    container_no: str
    numbers: dict[str, str]
    pi_date: date
    production_complete: date
    ci_date: date
    on_board: date
    eta: date
    coo_date: date
    boe_date: date
    payment_terms: str
    freight: Decimal
    insurance: Decimal
    duty: Decimal | None = None
    kg_per_unit: Decimal | None = None


def _party_address_cn(rng: random.Random, city: str, province: str) -> str:
    street = rng.choice(cat.SUPPLIER_STREETS)
    return f"No. {rng.randint(18, 288)} {street}, {city}, {province}, China"


def supplier_pool(seed: int, size: int = 14) -> list[Supplier]:
    rng = rng_for(seed, "suppliers")
    brands = list(cat.SUPPLIER_BRANDS)
    rng.shuffle(brands)
    pool: list[Supplier] = []
    for i in range(size):
        city, province = cat.SUPPLIER_CITIES[i % len(cat.SUPPLIER_CITIES)]
        kind = ("fabric", "fabric", "yarn", "accessory")[i % 4]
        word = rng.choice(cat.SUPPLIER_PRODUCT_WORDS[kind])
        name = f"{city} {brands[i % len(brands)]} {word} Co., Ltd."
        if any(s.party.name == name for s in pool):
            name = f"{city} {brands[(i + 5) % len(brands)]} {word} Co., Ltd."
        bank_name, code, cc, loc = rng.choice(cat.CN_BANKS)
        number = (
            f"SIM-CN-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"
        )
        pool.append(
            Supplier(
                party=Party(
                    name=name,
                    address=_party_address_cn(rng, city, province),
                    license_no=f"USCC-SIM-{rng.randint(10**12, 10**13 - 1)}",
                ),
                city=city,
                kind=kind,
                bank=BankDetails(
                    bank_name=bank_name,
                    holder_name=name,
                    account_masked=mask_account(number),
                    swift=f"{code}{cc}{loc}",
                    country=cc,
                ),
            )
        )
    return pool


def buyer_pool(seed: int, size: int = 12) -> list[Party]:
    rng = rng_for(seed, "buyers")
    words = list(cat.BUYER_WORDS)
    rng.shuffle(words)
    pool = []
    for i in range(size):
        city, area = cat.BUYER_CITIES[i % len(cat.BUYER_CITIES)]
        name = f"{words[i % len(words)]} {rng.choice(cat.BUYER_SUFFIXES)}"
        prefix = cat.TRADE_LICENCE_PREFIX[city]
        pool.append(
            Party(
                name=name,
                address=f"Plot {rng.randint(3, 96)}, {area}, Bangladesh",
                license_no=(
                    f"{prefix}-TL-SIM-{rng.randint(2016, 2024)}-{rng.randint(100, 9999):04d}"
                ),
            )
        )
    return pool


def _pick_goods(rng: random.Random, kind: str) -> cat.Goods:
    return rng.choice([g for g in cat.GOODS if g.kind == kind])


def describe(goods: cat.Goods, colour: str, rng: random.Random) -> tuple[str, int | None]:
    if goods.kind == "fabric":
        width, gsm = rng.choice(goods.widths_cm), rng.choice(goods.gsm)
        return f"{goods.name}, {gsm} gsm, width {width} cm, colour {colour}", width
    spec = rng.choice(goods.counts or goods.sizes)
    return f"{goods.name}, {spec}, colour {colour}", None


def plan_random(seed: int, index: int, suppliers: list[Supplier], buyers: list[Party]) -> Plan:
    rng = rng_for(seed, f"pack:{index}")
    supplier = rng.choice(suppliers)
    buyer = rng.choice(buyers)
    goods = _pick_goods(rng, supplier.kind)
    lo, hi = goods.band
    price = lo + (hi - lo) * D(str(round(rng.uniform(0.1, 0.9), 3)))
    price = price.quantize(D(1).scaleb(-goods.price_dp), rounding=ROUND_HALF_UP)
    qmin, qmax = goods.qty_range
    quantity = D(rng.randrange(qmin, qmax + 1, goods.qty_step))
    colour = rng.choice(cat.COLOURS)
    description, width = describe(goods, colour[0], rng)
    if supplier.city == "Guangzhou":
        pol = "Shenzhen" if rng.random() < 0.8 else "Shanghai"
    else:
        pol = "Ningbo" if rng.random() < 0.7 else "Shanghai"
    incoterm = f"FOB {pol}" if rng.random() < 0.8 else f"CFR {cat.PORT_OF_DISCHARGE}"
    carrier = rng.choice(cat.CARRIERS)
    vessel = f"MV {rng.choice(cat.VESSEL_PREFIXES)} {rng.choice(cat.VESSEL_NOUNS)}"
    voyage = f"{rng.randint(1, 99):03d}{rng.choice('EWSN')}"
    pi_date = date(2026, 1, 5) + timedelta(days=rng.randint(0, 250))
    production_complete = pi_date + timedelta(days=rng.randint(18, 35))
    on_board = production_complete + timedelta(days=rng.randint(2, 6))
    eta = on_board + timedelta(days=rng.randint(*cat.TRANSIT_DAYS))
    ci_date = on_board - timedelta(days=rng.randint(1, 3))
    n = scramble(index)
    prefix = "".join(w[0] for w in supplier.party.name.split()[1:3]).upper()
    bl_digits = rng.randint(10**7, 10**8 - 1)
    total = quantity * price
    return Plan(
        index=index,
        order_ref=f"SETU-SIM-{index + 1:04d}",
        supplier=supplier,
        buyer=buyer,
        goods=goods,
        colour=colour,
        description=description,
        width_cm=width,
        quantity=quantity,
        unit_price=price,
        per_pkg=rng.choice(goods.per_pkg),
        pol=pol,
        incoterm=incoterm,
        carrier=carrier,
        vessel=vessel,
        voyage=voyage,
        bl_no=f"{carrier[1]}{cat.PORT_CODES[pol]}{bl_digits}",
        container_no=container_number(carrier[2], rng.randint(0, 999_999)),
        numbers={
            "pi": f"{prefix}-PI-2026-{n % 1000:03d}-{index:04d}",
            "ci": f"{prefix}-CI-2026-{n:04d}",
            "pl": f"{prefix}-PL-2026-{n:04d}",
            "coo": f"CO-SIM-2026-{rng.randint(10**5, 10**6 - 1)}",
            "boe": f"BOE-SIM-2026-{rng.randint(10**5, 10**6 - 1)}",
        },
        pi_date=pi_date,
        production_complete=production_complete,
        ci_date=ci_date,
        on_board=on_board,
        eta=eta,
        coo_date=ci_date + timedelta(days=rng.randint(0, 1)),
        boe_date=eta + timedelta(days=rng.randint(0, 2)),
        payment_terms=rng.choice(PAYMENT_TERMS),
        freight=q2(max(D("300"), total * D("0.06"))),
        insurance=q2(total * D("0.005")),
    )


def style_random(seed: int, index: int) -> RenderStyle:
    rng = rng_for(seed, f"style:{index}")
    return RenderStyle(
        font=rng.choices(("helvetica", "times", "courier"), weights=(5, 3, 2))[0],
        date_fmt=rng.choice(DATE_FORMATS),
        order_seed=rng.randint(0, 10**6),
    )


def _incoterm_port(incoterm: str) -> str:
    return incoterm.split(" ", 1)[1]


def build_pack(plan: Plan, style: RenderStyle, seed: int) -> Pack:
    g, s = plan.goods, plan.supplier
    total = q2(plan.quantity * plan.unit_price)
    pol, pod = plan.pol, cat.PORT_OF_DISCHARGE
    packages = math.ceil(plan.quantity / plan.per_pkg)
    kg = plan.kg_per_unit if plan.kg_per_unit is not None else g.kg_per_unit
    net = q2(plan.quantity * kg)
    gross = q2(net + packages * g.tare_kg)

    deal = DealTerms(
        order_ref=plan.order_ref,
        supplier_license_name=s.party.name,
        supplier_license_no=s.party.license_no or "",
        registered_bank=s.bank,
        buyer=plan.buyer,
        hs_code=g.hs,
        unit=g.unit,
        price_band=g.band,
        port_of_loading=pol,
        port_of_discharge=pod,
        incoterm=plan.incoterm,
        booked_vessel=plan.vessel,
        booked_voyage=plan.voyage,
        production_complete=plan.production_complete,
        eta=plan.eta,
    )
    schedule = Schedule(
        booked_vessel=plan.vessel,
        booked_voyage=plan.voyage,
        production_complete=plan.production_complete,
        est_ship_date=plan.on_board,
        eta=plan.eta,
    )

    def invoice(kind: str, number: str, when: date, sched: Schedule | None) -> InvoiceDoc:
        return InvoiceDoc(
            doc_type=kind,  # type: ignore[arg-type]
            invoice_no=number,
            date=when,
            seller=s.party,
            buyer=plan.buyer,
            goods_description=plan.description,
            hs_code=g.hs,
            quantity=plan.quantity,
            unit=g.unit,
            unit_price=plan.unit_price,
            total=total,
            incoterm=plan.incoterm,
            payment_terms=plan.payment_terms,
            bank=s.bank,
            port_of_loading=pol,
            port_of_discharge=pod,
            schedule=sched,
        )

    proforma = invoice("PROFORMA_INVOICE", plan.numbers["pi"], plan.pi_date, schedule)
    commercial = invoice("COMMERCIAL_INVOICE", plan.numbers["ci"], plan.ci_date, None)
    packing = PackingListDoc(
        pl_no=plan.numbers["pl"],
        date=plan.ci_date,
        invoice_no=plan.numbers["ci"],
        seller=s.party,
        buyer=plan.buyer,
        goods_description=plan.description,
        packages=packages,
        package_type=g.pkg_type,
        quantity=plan.quantity,
        unit=g.unit,
        net_weight_kg=net,
        gross_weight_kg=gross,
        marks=f"{plan.buyer.name.split()[0].upper()} / {plan.order_ref} / C/NO 1-{packages}",
    )
    bol = BillOfLadingDoc(
        bl_no=plan.bl_no,
        carrier=plan.carrier[0],
        shipper=s.party,
        consignee=plan.buyer,
        notify_party=plan.buyer,
        vessel=plan.vessel,
        voyage=plan.voyage,
        port_of_loading=pol,
        port_of_discharge=pod,
        on_board_date=plan.on_board,
        container_no=plan.container_no,
        description=plan.description,
        packages=packages,
        package_type=g.pkg_type,
        quantity=plan.quantity,
        unit=g.unit,
        gross_weight_kg=gross,
        freight_terms="FREIGHT COLLECT" if plan.incoterm.startswith("FOB") else "FREIGHT PREPAID",
    )
    coo = CertOfOriginDoc(
        coo_no=plan.numbers["coo"],
        exporter=s.party,
        consignee=plan.buyer,
        origin_country="China",
        hs_code=g.hs,
        description=plan.description,
        quantity=plan.quantity,
        unit=g.unit,
        issue_date=plan.coo_date,
        issuing_body=cat.ISSUING_BODY,
    )
    assessed = q2(total + plan.freight + plan.insurance)
    duty = plan.duty if plan.duty is not None else q2(assessed * g.duty_rate)
    fx = cat.FOREIGN_FX_RATE_USD_BDT
    boe = BillOfEntryDoc(
        boe_no=plan.numbers["boe"],
        date=plan.boe_date,
        importer=plan.buyer,
        port=pod,
        bl_no=plan.bl_no,
        hs_code=g.hs,
        description=plan.description,
        quantity=plan.quantity,
        unit=g.unit,
        assessed_value_usd=assessed,
        duty_usd=duty,
        fx_usd_bdt=fx,
        assessed_value_bdt=q2(assessed * fx),
        duty_bdt=q2(duty * fx),
    )
    photos = []
    for i in (1, 2):
        pr = rng_for(seed, f"photo:{plan.index}:{i}")
        photos.append(
            PhotoDoc(
                file_name=f"production_photo_{i}.jpg",
                color_name=plan.colour[0],
                rgb=plan.colour[1],
                width_cm=plan.width_cm,
                capture_date=plan.pi_date
                + timedelta(
                    days=pr.randint(4, max(5, (plan.production_complete - plan.pi_date).days))
                ),
                caption=f"Production run, {plan.colour[0]}"
                + (f", width {plan.width_cm} cm" if plan.width_cm else ""),
                seed=pr.randint(0, 2**31 - 1),
            )
        )
    return Pack(
        pack_id="UNASSIGNED",
        seed=seed,
        index=plan.index,
        deal=deal,
        style=style,
        proforma=proforma,
        invoice=commercial,
        packing_list=packing,
        bill_of_lading=bol,
        coo=coo,
        boe=boe,
        photos=photos,
    )


def clean_pack(seed: int, index: int, suppliers: list[Supplier], buyers: list[Party]) -> Pack:
    return build_pack(plan_random(seed, index, suppliers, buyers), style_random(seed, index), seed)
