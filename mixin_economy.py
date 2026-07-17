import traceback
import datetime
import random
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger

class EconomyMixin:
    """经济系统：签到、转账"""

    @filter.command("签到")
    async def daily_sign(self, event: AstrMessageEvent):
        try:
            user_id = event.get_sender_id()
            neko = await self.get_neko(user_id)
            if not neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            today = datetime.date.today().isoformat()
            if neko.get("last_sign_date") == today:
                yield event.plain_result(f"{neko['neko_name']} 今天已经签到过了喵～明天再来吧！")
                return

            reward = random.randint(10, 50)
            new_balance = neko.get("maotiao", 0) + reward

            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "maotiao": new_balance,
                    "last_sign_date": today
                }}
            )
            yield event.plain_result(
                f"{neko['neko_name']} 签到成功！获得了 {reward} 根猫条，当前余额：{new_balance} 根喵～"
            )
        except Exception as e:
            logger.error(f"/签到 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("转账")
    async def transfer(self, event: AstrMessageEvent):
        try:
            parts = event.message_str.split()
            if len(parts) < 3:
                yield event.plain_result("参数错误，格式：/转账 猫娘名字 数量")
                return
            target_name = parts[1]
            try:
                amount = int(parts[2])
            except ValueError:
                yield event.plain_result("数量必须是整数喵～")
                return
            if amount <= 0:
                yield event.plain_result("转账数量必须大于 0 喵～")
                return

            user_id = event.get_sender_id()
            sender = await self.get_neko(user_id)
            if not sender:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            sender_balance = sender.get("maotiao", 0)
            if sender_balance < amount:
                yield event.plain_result(f"{sender['neko_name']} 的猫条不足，只有 {sender_balance} 根喵～")
                return

            receiver = await self.collection.find_one({"neko_name": target_name})
            if not receiver:
                yield event.plain_result("找不到该猫娘，请检查名字喵～")
                return
            if receiver["user_id"] == user_id:
                yield event.plain_result("不能转账给自己喵～")
                return

            await self.collection.update_one(
                {"user_id": user_id},
                {"$inc": {"maotiao": -amount}}
            )
            await self.collection.update_one(
                {"user_id": receiver["user_id"]},
                {"$inc": {"maotiao": amount}}
            )
            new_balance = sender_balance - amount
            yield event.plain_result(
                f"{sender['neko_name']} 向 {receiver['neko_name']} 转账 {amount} 根猫条成功！余额：{new_balance} 根喵～"
            )
        except Exception as e:
            logger.error(f"/转账 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")