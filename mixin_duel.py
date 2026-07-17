import traceback
import datetime
import random
from datetime import timezone
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger

class DuelMixin:
    """决斗系统：发起、接受、拒绝、列表"""

    @filter.command("决斗")
    async def duel(self, event: AstrMessageEvent):
        """发起决斗：/决斗 猫娘名字 赌注 你的猜测数字"""
        try:
            parts = event.message_str.split()
            if len(parts) < 4:
                yield event.plain_result("参数错误，格式：/决斗 猫娘名字 赌注 猜测数字")
                return
            target_name = parts[1]
            try:
                bet = int(parts[2])
                guess = int(parts[3])
            except ValueError:
                yield event.plain_result("赌注和猜测数字必须是整数喵～")
                return
            if bet <= 0:
                yield event.plain_result("赌注必须大于0喵～")
                return
            if not (0 <= guess <= 100):
                yield event.plain_result("猜测数字需要在0~100之间喵～")
                return

            user_id = event.get_sender_id()
            my_neko = await self.get_neko(user_id)
            if not my_neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            target_neko = await self.collection.find_one({"neko_name": target_name})
            if not target_neko:
                yield event.plain_result(f"找不到名为 {target_name} 的猫娘喵～")
                return

            if target_neko["user_id"] == user_id:
                yield event.plain_result("不能和自己的猫娘决斗喵～")
                return

            if my_neko.get("maotiao", 0) < bet:
                yield event.plain_result(f"{my_neko['neko_name']} 的猫条不足，只有 {my_neko['maotiao']} 根喵～")
                return

            # 检查是否已有待处理的邀请
            existing = await self.duel_collection.find_one({
                "inviter_uid": user_id,
                "target_uid": target_neko["user_id"],
                "status": "pending"
            })
            if existing:
                yield event.plain_result(f"你已经向 {target_name} 发起了决斗邀请，等待对方回应喵～")
                return

            await self.duel_collection.insert_one({
                "inviter_uid": user_id,
                "target_uid": target_neko["user_id"],
                "bet": bet,
                "inviter_guess": guess,
                "status": "pending",
                "created_at": datetime.datetime.now(timezone.utc)
            })
            yield event.plain_result(
                f"{my_neko['neko_name']} 向 {target_name} 发起了决斗！赌注 {bet} 猫条，你的猜测：{guess}\n"
                f"等待对方通过 `/接受决斗 {my_neko['neko_name']} <猜测>` 应战喵～"
            )
        except Exception as e:
            logger.error(f"/决斗 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("接受决斗")
    async def accept_duel(self, event: AstrMessageEvent):
        """接受决斗：/接受决斗 发起者猫娘名字 你的猜测数字"""
        try:
            parts = event.message_str.split()
            if len(parts) < 3:
                yield event.plain_result("参数错误，格式：/接受决斗 发起者猫娘名字 猜测数字")
                return
            inviter_name = parts[1]
            try:
                guess = int(parts[2])
            except ValueError:
                yield event.plain_result("猜测数字必须是整数喵～")
                return
            if not (0 <= guess <= 100):
                yield event.plain_result("猜测数字需要在0~100之间喵～")
                return

            user_id = event.get_sender_id()
            my_neko = await self.get_neko(user_id)
            if not my_neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            # 找到发起者
            inviter_neko = await self.collection.find_one({"neko_name": inviter_name})
            if not inviter_neko:
                yield event.plain_result(f"找不到名为 {inviter_name} 的猫娘喵～")
                return

            # 找到对应的邀请
            invite = await self.duel_collection.find_one({
                "inviter_uid": inviter_neko["user_id"],
                "target_uid": user_id,
                "status": "pending"
            })
            if not invite:
                yield event.plain_result(f"没有来自 {inviter_name} 的决斗邀请喵～")
                return

            bet = invite["bet"]
            if my_neko.get("maotiao", 0) < bet:
                yield event.plain_result(f"{my_neko['neko_name']} 的猫条不足，无法接战，需要 {bet} 根猫条喵～")
                return

            # 生成系统随机数
            secret = random.randint(0, 100)
            inviter_guess = invite["inviter_guess"]
            # 计算差值
            diff1 = abs(inviter_guess - secret)
            diff2 = abs(guess - secret)

            if diff1 < diff2:
                winner_uid = invite["inviter_uid"]
                loser_uid = user_id
                winner_guess = inviter_guess
                loser_guess = guess
            elif diff2 < diff1:
                winner_uid = user_id
                loser_uid = invite["inviter_uid"]
                winner_guess = guess
                loser_guess = inviter_guess
            else:  # 平局
                # 赌注不转移，删除邀请
                await self.duel_collection.delete_one({"_id": invite["_id"]})
                yield event.plain_result(
                    f"⚔️ 决斗结果：平局！系统数字 {secret}\n"
                    f"{inviter_name} 猜 {inviter_guess}，{my_neko['neko_name']} 猜 {guess}，一样接近喵～"
                )
                return

            # 执行转账
            await self.collection.update_one(
                {"user_id": loser_uid},
                {"$inc": {"maotiao": -bet}}
            )
            await self.collection.update_one(
                {"user_id": winner_uid},
                {"$inc": {"maotiao": bet}}
            )

            # 删除邀请
            await self.duel_collection.delete_one({"_id": invite["_id"]})

            winner_neko = await self.get_neko(winner_uid)
            loser_neko = await self.get_neko(loser_uid)
            winner_name = winner_neko["neko_name"] if winner_neko else "未知"
            loser_name = loser_neko["neko_name"] if loser_neko else "未知"

            yield event.plain_result(
                f"⚔️ 决斗结束！系统数字：{secret}\n"
                f"{winner_name} 猜 {winner_guess}，{loser_name} 猜 {loser_guess}\n"
                f"{winner_name} 获胜！赢得 {bet} 猫条喵～"
            )
        except Exception as e:
            logger.error(f"/接受决斗 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("拒绝决斗")
    async def reject_duel(self, event: AstrMessageEvent):
        """拒绝决斗：/拒绝决斗 发起者猫娘名字"""
        try:
            parts = event.message_str.split()
            if len(parts) < 2:
                yield event.plain_result("参数错误，格式：/拒绝决斗 发起者猫娘名字")
                return
            inviter_name = parts[1]

            user_id = event.get_sender_id()
            inviter_neko = await self.collection.find_one({"neko_name": inviter_name})
            if not inviter_neko:
                yield event.plain_result(f"找不到名为 {inviter_name} 的猫娘喵～")
                return

            result = await self.duel_collection.delete_one({
                "inviter_uid": inviter_neko["user_id"],
                "target_uid": user_id,
                "status": "pending"
            })
            if result.deleted_count == 0:
                yield event.plain_result(f"没有来自 {inviter_name} 的决斗邀请或已处理喵～")
                return

            my_neko = await self.get_neko(user_id)
            my_name = my_neko["neko_name"] if my_neko else "你"
            yield event.plain_result(f"{my_name} 拒绝了 {inviter_name} 的决斗邀请喵～")
        except Exception as e:
            logger.error(f"/拒绝决斗 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("决斗列表")
    async def duel_list(self, event: AstrMessageEvent):
        """查看我收到的待处理决斗邀请"""
        try:
            user_id = event.get_sender_id()
            invites = await self.duel_collection.find(
                {"target_uid": user_id, "status": "pending"}
            ).to_list(length=10)

            if not invites:
                yield event.plain_result("你当前没有未处理的决斗邀请喵～")
                return

            neko = await self.get_neko(user_id)
            name = neko["neko_name"] if neko else "你"
            lines = [f"⚔️ {name} 收到的决斗邀请："]
            for inv in invites:
                inviter = await self.get_neko(inv["inviter_uid"])
                inviter_name = inviter["neko_name"] if inviter else "未知"
                lines.append(f"来自 {inviter_name}，赌注：{inv['bet']} 猫条")
            lines.append("\n使用 /接受决斗 <发起者> <你的猜测> 应战，或 /拒绝决斗 <发起者> 拒绝")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"/决斗列表 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")