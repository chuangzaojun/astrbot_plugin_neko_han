import datetime
from datetime import timezone
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
import motor.motor_asyncio
from .const import DEFAULT_STAMINA
from .mixin_basic import BasicMixin
from .mixin_economy import EconomyMixin
from .mixin_marriage import MarriageMixin
from .mixin_labor import LaborMixin
from .mixin_duel import DuelMixin

@register("neko_han", "Neko_Han", "喵喵喵", "0.3")
class NekoHan(Star, BasicMixin, EconomyMixin, MarriageMixin, LaborMixin, DuelMixin):
    def __init__(self, context: Context):
        super().__init__(context)
        self.client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
        self.db = self.client["neko-han"]
        self.collection = self.db["nekoes"]
        self.labor_collection = self.db["labor_hall"]
        self.duel_collection = self.db["duel_invites"]
        self.last_refresh_time = None

    async def initialize(self):
        try:
            await self.client.admin.command("ping")
            logger.info("neko-han 数据库连接成功")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")

    async def get_neko(self, user_id: str):
        return await self.collection.find_one({"user_id": user_id})

    async def reset_daily_stamina(self, user_id: str, neko_doc: dict = None):
        if neko_doc is None:
            neko_doc = await self.get_neko(user_id)
            if neko_doc is None:
                return False, DEFAULT_STAMINA

        today_str = datetime.date.today().isoformat()
        last_date = neko_doc.get("last_stamina_date", "")
        if last_date != today_str:
            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"stamina": DEFAULT_STAMINA, "last_stamina_date": today_str}}
            )
            return True, DEFAULT_STAMINA
        return False, neko_doc.get("stamina", DEFAULT_STAMINA)

    @filter.command("你能做什么")
    async def help(self, event: AstrMessageEvent):
        help_text = (
            "🐱 **Neko_Han 猫娘养成系统帮助**\n\n"
            "👋 基础互动\n"
            "  • `/喵` — 让 Neko_Han 和你打个招呼\n"
            "  • `/你是猫娘么` — 问它是不是猫娘\n\n"
            "🐈 猫娘养成\n"
            "  • `/创建猫娘 <名字>` — 创建属于你的猫娘（名字须无空格）\n"
            "  • `/改名 <新名字>` — 修改你的猫娘名字\n"
            "  • `/仪表盘` — 查看猫娘状态（名字、猫条、体力、婚恋、劳务、决斗邀请）\n\n"
            "💰 经济系统\n"
            "  • `/签到` — 每日签到，随机获得 10~50 猫条\n"
            "  • `/转账 <猫娘名字> <数量>` — 向其他猫娘转账猫条\n\n"
            "🏗️ 劳动系统\n"
            "  • `/猫力资源市场` — 查看可接劳务任务（每小时刷新）\n"
            "  • `/接取劳务 <序号>` — 接取任务，消耗体力，完成后得猫条\n"
            "  • `/我的劳务` — 查看进行中的任务\n"
            "  • `/取消劳务 <序号>` — 取消任务（体力不返还）\n\n"
            "💕 婚恋系统\n"
            "  • `/求婚 <猫娘名字>` — 让你的猫娘向其他猫娘求婚\n"
            "  • `/接受求婚 <猫娘名字>` — 接受对方的求婚\n"
            "  • `/离婚` — 与当前配偶离婚\n"
            "  • `/求婚列表` — 查看收到的求婚请求（类似决斗列表）\n\n"
            "⚔️ 决斗系统\n"
            "  • `/决斗 <猫娘名字> <赌注> <你的猜测>` — 向其他猫娘发起决斗\n"
            "  • `/接受决斗 <发起者猫娘名字> <你的猜测>` — 应战\n"
            "  • `/拒绝决斗 <发起者猫娘名字>` — 拒绝决斗\n"
            "  • `/决斗列表` — 查看收到的决斗邀请\n\n"
            "❓ 帮助\n"
            "  • `/你能做什么` — 显示本帮助信息\n\n"
            "💡 提示：所有猫娘关系通过用户 ID 绑定，体力每日重置，劳动大厅每小时刷新喵~"
        )
        yield event.plain_result(help_text)

    async def terminate(self):
        self.client.close()