import traceback
import datetime
from datetime import timezone
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
import astrbot.api.message_components as Comp
from .const import DEFAULT_STAMINA

class BasicMixin:
    """基础互动和猫娘养成命令"""

    @filter.command("喵")
    async def miao(self, event: AstrMessageEvent):
        try:
            user_id = event.get_sender_id()
            neko = await self.get_neko(user_id)
            name = neko["neko_name"] if neko else None
            if name:
                text = f"喵喵喵～{name}，我是由 Stalyx（创造君）开发的聊天机器人 Neko_Han 喵～"
            else:
                text = "喵喵喵～我是由 Stalyx（创造君）开发的聊天机器人 Neko_Han 喵～"
            yield event.chain_result([Comp.At(qq=user_id), Comp.Plain(text)])
        except Exception as e:
            logger.error(f"/喵 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("你是猫娘么")
    async def are_you_neko(self, event: AstrMessageEvent):
        yield event.plain_result("是的喵～")

    @filter.command("创建猫娘")
    async def create_neko(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if len(args) != 1:
                yield event.plain_result("参数错误，需要一个无空格字符串作为猫娘名字")
                return
            user_id = event.get_sender_id()
            neko_name = args[0]

            if await self.get_neko(user_id):
                yield event.plain_result("你已经有猫娘了，不能重复创建喵～")
                return
            if await self.collection.find_one({"neko_name": neko_name}):
                yield event.plain_result("猫娘名字已经被占用，请换个名字喵～")
                return

            await self.collection.insert_one({
                "user_id": user_id,
                "neko_name": neko_name,
                "maotiao": 100,
                "stamina": DEFAULT_STAMINA,
                "last_stamina_date": ""
            })
            yield event.plain_result(f"{neko_name} 现在是你的猫娘喵～")
        except Exception as e:
            logger.error(f"/创建猫娘 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("改名")
    async def rename_neko(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if len(args) != 1:
                yield event.plain_result("参数错误，需要一个无空格字符串作为新名字")
                return

            user_id = event.get_sender_id()
            new_name = args[0]

            my_neko = await self.get_neko(user_id)
            if not my_neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            existing = await self.collection.find_one({"neko_name": new_name})
            if existing and existing["user_id"] != user_id:
                yield event.plain_result("新名字已经被其他猫娘占用，请换个名字喵～")
                return

            old_name = my_neko["neko_name"]
            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"neko_name": new_name}}
            )
            yield event.plain_result(f"{old_name} 已更名为 {new_name} 喵～")
        except Exception as e:
            logger.error(f"/改名 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("仪表盘")
    async def dashboard(self, event: AstrMessageEvent):
        try:
            user_id = event.get_sender_id()
            my_neko = await self.get_neko(user_id)
            if not my_neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            # 每日体力重置
            is_new_day, current_stamina = await self.reset_daily_stamina(user_id, my_neko)
            if is_new_day:
                my_neko["stamina"] = current_stamina

            neko_name = my_neko["neko_name"]
            maotiao = my_neko.get("maotiao", 0)
            stamina = my_neko.get("stamina", DEFAULT_STAMINA)

            status_lines = [
                f"🐱 {neko_name} 的仪表盘",
                f"🐾 猫条余额：{maotiao} 根",
                f"⚡ 体力：{stamina}/{DEFAULT_STAMINA}"
            ]

            # 婚恋状态
            wife_uid = my_neko.get("wife")
            if wife_uid:
                partner = await self.get_neko(wife_uid)
                partner_name = partner["neko_name"] if partner else "未知猫娘"
                status_lines.append(f"💍 已婚，配偶：{partner_name}")
            else:
                proposing_to_uid = my_neko.get("proposing_to")
                if proposing_to_uid:
                    target = await self.get_neko(proposing_to_uid)
                    target_name = target["neko_name"] if target else "未知猫娘"
                    status_lines.append(f"💌 正在向 {target_name} 求婚")
                else:
                    status_lines.append("💔 单身")

            # 决斗邀请
            invites = await self.duel_collection.find(
                {"target_uid": user_id, "status": "pending"}
            ).to_list(length=10)
            if invites:
                status_lines.append("")
                status_lines.append("⚔️ **收到的决斗邀请**")
                for inv in invites:
                    inviter = await self.get_neko(inv["inviter_uid"])
                    inviter_name = inviter["neko_name"] if inviter else "未知猫娘"
                    status_lines.append(
                        f"来自 {inviter_name} 的挑战，赌注：{inv['bet']} 猫条 (输入 /接受决斗 {inviter_name} <你的猜测> 应战)"
                    )

            # 劳务状态
            status_lines.append("")
            await self.auto_complete_tasks(user_id)
            labor_tasks = await self.labor_collection.find(
                {"worker_id": user_id, "status": "in_progress"}
            ).to_list(length=10)

            if labor_tasks:
                status_lines.append("🔧 **进行中的劳务**")
                for i, t in enumerate(labor_tasks, 1):
                    emoji = t.get("emoji", "🐾")
                    name = t.get("name", "劳务")
                    cost = t["cost"]
                    reward = t["reward"]
                    end_time = t["end_time"].replace(tzinfo=timezone.utc)
                    remaining = end_time - datetime.datetime.now(timezone.utc)
                    if remaining.total_seconds() <= 0:
                        remaining_str = "已完成"
                    else:
                        mins = int(remaining.total_seconds() // 60)
                        secs = int(remaining.total_seconds() % 60)
                        remaining_str = f"{mins}分{secs}秒"
                    status_lines.append(
                        f"{i}. {emoji}{name} | 消耗{cost}体 | 🐾{reward}猫条 | 剩余：{remaining_str}"
                    )
                status_lines.append("（输入 /取消劳务 序号 可取消，体力不返还）")
            else:
                status_lines.append("🔧 当前无进行中的劳务（前往 /猫力资源市场 看看吧）")

            yield event.plain_result("\n".join(status_lines))
        except Exception as e:
            logger.error(f"/仪表盘 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")