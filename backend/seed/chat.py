"""One Bangla chat thread for Rahima so the chat page is not empty. Numbers come from the seed
data.
"""

from app.db.enums import ChatRole, CostKind, Language
from app.db.models import ChatMessage, ChatThread
from seed.alerts_approvals import shortfall_facts, usd
from seed.common import Ctx, Rows, sid
from seed.deals import DEALS_BY_REF, MAIN_DEAL
from seed.users import user_id

THREAD = "chat:rahima:main-deal"


def build(ctx: Ctx) -> Rows:
    sf = shortfall_facts(ctx)
    main = DEALS_BY_REF[MAIN_DEAL]
    landed = main.landed_cost().amount

    def cost(kind: CostKind) -> str:
        return usd(main.costs[kind][0])

    messages = [
        (ChatRole.USER, f"{MAIN_DEAL} অর্ডারের মোট খরচ কত, আর মাইলস্টোন ২-এর টাকা দিতে পারব তো?"),
        (
            ChatRole.ASSISTANT,
            f"{MAIN_DEAL}-এর মোট আমদানি খরচ (ল্যান্ডেড কস্ট) {usd(landed)}: পণ্য "
            f"{usd(main.goods_value.amount)}, ফ্রেইট {cost(CostKind.FREIGHT)}, বিমা "
            f"{cost(CostKind.INSURANCE)}, শুল্ক {cost(CostKind.DUTY)} এবং ব্যাংক চার্জ "
            f"{cost(CostKind.BANK_CHARGES)}। {sf['date'].isoformat()} তারিখে মাইলস্টোন ২-এর জন্য "
            f"{usd(sf['due'])} লাগবে, কিন্তু আপনার আনুমানিক ব্যালেন্স হবে {usd(sf['balance'])} — "
            f"ঘাটতি {usd(sf['shortfall'])}। (সিমুলেটেড ডেটা)",
        ),
        (ChatRole.USER, "ঠিক আছে। এই ঘাটতি মেটানোর জন্য অর্থায়নের বিকল্পগুলো দেখাও।"),
    ]
    thread = {
        "id": sid("chat_thread", THREAD),
        "user_id": user_id("rahima@demo.setu"),
        "title": f"{MAIN_DEAL} — খরচ ও নগদ প্রবাহ",
        "language": Language.BN,
        "created_at": ctx.at(-1, 18, 0),
    }
    rows = [
        {
            "id": sid("chat_message", f"{THREAD}:{seq}"),
            "thread_id": thread["id"],
            "seq": seq,
            "role": role,
            "content": content,
            "created_at": ctx.at(-1, 18, seq),
        }
        for seq, (role, content) in enumerate(messages, start=1)
    ]
    return [(ChatThread, [thread]), (ChatMessage, rows)]
