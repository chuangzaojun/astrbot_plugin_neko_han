import traceback
import datetime
import random
from datetime import timezone, timedelta
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp
import motor.motor_asyncio

# ---------- 原硬编码常量已移除，全部改用配置 ----------

@register("neko_han", "Neko_Han", "喵喵喵", "0.3")
class NekoHan(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 使用配置中的数据库连接信息
        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.config["MONGO_URI"])
        self.db = self.client[self.config["DB_NAME"]]
        self.collection = self.db[self.config["NEKO_COLLECTION"]]
        self.labor_collection = self.db[self.config["LABOR_COLLECTION"]]
        self.duel_collection = self.db[self.config["DUEL_COLLECTION"]]
        self.last_refresh_time = None

    async def initialize(self):
        try:
            await self.client.admin.command("ping")
            logger.info("neko-han 数据库连接成功")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")

    async def get_neko(self, user_id: str):
        """安全获取猫娘文档，无则返回 None"""
        return await self.collection.find_one({"user_id": user_id})

    async def reset_daily_stamina(self, user_id: str, neko_doc: dict = None):
        if neko_doc is None:
            neko_doc = await self.get_neko(user_id)
            if neko_doc is None:
                return False, self.config["DEFAULT_STAMINA"]

        today_str = datetime.date.today().isoformat()
        last_date = neko_doc.get("last_stamina_date", "")
        if last_date != today_str:
            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"stamina": self.config["DEFAULT_STAMINA"], "last_stamina_date": today_str}}
            )
            return True, self.config["DEFAULT_STAMINA"]
        return False, neko_doc.get("stamina", self.config["DEFAULT_STAMINA"])

    async def refresh_labor_hall(self):
        now = datetime.datetime.now(timezone.utc)
        if self.last_refresh_time and (now - self.last_refresh_time).total_seconds() < self.config["LABOR_REFRESH_INTERVAL"]:
            return

        await self.labor_collection.delete_many({"status": {"$ne": "in_progress"}})

        new_tasks = []
        for _ in range(self.config["LABOR_HALL_SIZE"]):
            cost = random.randint(50, 200)
            duration = random.randint(5 * 60, 30 * 60)  # 5~30分钟（秒）
            reward = cost * 2 + random.randint(0, cost // 2)
            task_desc = random.choice(self.config["LABOR_TASKS"])
            new_tasks.append({
                "name": task_desc["name"],
                "emoji": task_desc["emoji"],
                "cost": cost,
                "duration": duration,
                "reward": reward,
                "status": "available",
                "worker_id": None,
                "start_time": None,
                "end_time": None
            })
        if new_tasks:
            await self.labor_collection.insert_many(new_tasks)
        self.last_refresh_time = now

    async def auto_complete_tasks(self, user_id: str = None):
        now = datetime.datetime.now(timezone.utc)
        query = {"status": "in_progress", "end_time": {"$lte": now}}
        if user_id:
            query["worker_id"] = user_id

        tasks = await self.labor_collection.find(query).to_list(length=100)
        completed = 0
        for t in tasks:
            await self.collection.update_one(
                {"user_id": t["worker_id"]},
                {"$inc": {"maotiao": t["reward"]}}
            )
            await self.labor_collection.update_one(
                {"_id": t["_id"]},
                {"$set": {"status": "completed", "completed_time": now}}
            )
            completed += 1
        return completed

    # ================= 指令区域 =================

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
                "maotiao": self.config["INITIAL_MAOTIAO"],
                "stamina": self.config["DEFAULT_STAMINA"],
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
            logger.error(f"/修改名字 错误:\n{traceback.format_exc()}")
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
            stamina = my_neko.get("stamina", self.config["DEFAULT_STAMINA"])

            status_lines = [
                f"🐱 {neko_name} 的仪表盘",
                f"🐾 猫条余额：{maotiao} 根",
                f"⚡ 体力：{stamina}/{self.config['DEFAULT_STAMINA']}"
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
                        f"{i}. {emoji}{name} | 消耗{cost}体力 | 🐾{reward}猫条 | 剩余：{remaining_str}"
                    )
                status_lines.append("（输入 /取消劳务 序号 可取消，体力不返还）")
            else:
                status_lines.append("🔧 当前无进行中的劳务（前往 /猫力资源市场 看看吧）")

            yield event.plain_result("\n".join(status_lines))
        except Exception as e:
            logger.error(f"/仪表盘 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("求婚")
    async def propose_marriage(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if len(args) != 1:
                yield event.plain_result("参数错误，需要一个无空格字符串作为求婚对象的名字")
                return
            user_id = event.get_sender_id()
            target_name = args[0]

            my_neko = await self.get_neko(user_id)
            if not my_neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return
            if my_neko.get("wife"):
                yield event.plain_result(f"{my_neko['neko_name']} 已经有配偶了，不能再求婚喵～")
                return

            target_neko = await self.collection.find_one({"neko_name": target_name})
            if not target_neko:
                yield event.plain_result("找不到名为该名称的猫娘喵～")
                return

            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"proposing_to": target_neko["user_id"]}}
            )
            yield event.plain_result(
                f"{my_neko['neko_name']} 正在向 {target_neko['neko_name']} 求婚，等待对方同意喵～"
            )
        except Exception as e:
            logger.error(f"/求婚 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("接受求婚")
    async def accept_marriage(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if len(args) != 1:
                yield event.plain_result("参数错误，需要一个无空格字符串作为求婚对象的名字")
                return
            user_id = event.get_sender_id()
            target_name = args[0]

            my_neko = await self.get_neko(user_id)
            if not my_neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return
            if my_neko.get("wife"):
                yield event.plain_result(f"{my_neko['neko_name']} 已经有配偶了，不能再接受求婚喵～")
                return

            proposer_neko = await self.collection.find_one({
                "neko_name": target_name,
                "proposing_to": user_id
            })
            if not proposer_neko:
                yield event.plain_result("未找到来自该猫娘的有效求婚请求喵～")
                return

            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"wife": proposer_neko["user_id"]}}
            )
            await self.collection.update_one(
                {"user_id": proposer_neko["user_id"]},
                {"$set": {"wife": user_id}, "$unset": {"proposing_to": ""}}
            )
            yield event.plain_result(
                f"{my_neko['neko_name']} 接受了 {proposer_neko['neko_name']} 的求婚，百年好合喵～"
            )
        except Exception as e:
            logger.error(f"/接受求婚 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("离婚")
    async def divorce(self, event: AstrMessageEvent):
        try:
            user_id = event.get_sender_id()
            my_neko = await self.get_neko(user_id)
            if not my_neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            partner_id = my_neko.get("wife")
            if not partner_id:
                yield event.plain_result(f"{my_neko['neko_name']} 目前单身喵～")
                return

            await self.collection.update_one(
                {"user_id": user_id},
                {"$unset": {"wife": ""}}
            )
            result = await self.collection.update_one(
                {"user_id": partner_id},
                {"$unset": {"wife": ""}}
            )

            partner_neko = await self.get_neko(partner_id)
            partner_display = partner_neko["neko_name"] if partner_neko else "未知猫娘"
            if result.modified_count == 0:
                yield event.plain_result(f"{my_neko['neko_name']} 和 {partner_display} 离婚成功，但对方可能已消失喵～")
            else:
                yield event.plain_result(f"{my_neko['neko_name']} 和 {partner_display} 离婚了喵～")
        except Exception as e:
            logger.error(f"/离婚 错误:\n{traceback.format_exc()}")
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

            reward = random.randint(self.config["SIGN_REWARD_MIN"], self.config["SIGN_REWARD_MAX"])
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

    # ---------- 决斗系统 ----------
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
            if not (self.config["DUEL_GUESS_MIN"] <= guess <= self.config["DUEL_GUESS_MAX"]):
                yield event.plain_result(f"猜测数字需要在{self.config['DUEL_GUESS_MIN']}~{self.config['DUEL_GUESS_MAX']}之间喵～")
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
            if not (self.config["DUEL_GUESS_MIN"] <= guess <= self.config["DUEL_GUESS_MAX"]):
                yield event.plain_result(f"猜测数字需要在{self.config['DUEL_GUESS_MIN']}~{self.config['DUEL_GUESS_MAX']}之间喵～")
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

            # 生成系统随机数（范围包含所有可能猜测值）
            secret = random.randint(self.config["DUEL_GUESS_MIN"] - 1, self.config["DUEL_GUESS_MAX"])
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

    # ---------- 劳务系统 ----------
    @filter.command("猫力资源市场")
    async def labor_hall(self, event: AstrMessageEvent):
        try:
            user_id = event.get_sender_id()
            neko = await self.get_neko(user_id)
            if not neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            await self.refresh_labor_hall()
            tasks = await self.labor_collection.find({"status": "available"}).to_list(length=self.config["LABOR_HALL_SIZE"])

            if not tasks:
                yield event.plain_result(f"{neko['neko_name']}，猫力资源市场暂时没有可接的劳务喵～等下次刷新吧！")
                return

            lines = [f"🏗️ {neko['neko_name']}，猫力资源市场的任务列表"]
            for i, t in enumerate(tasks, 1):
                emoji = t.get("emoji", "🐾")
                name = t.get("name", "临时任务")
                cost = t["cost"]
                duration = t["duration"]
                reward = t["reward"]
                mins = duration // 60
                secs = duration % 60
                time_str = f"{mins}分{secs}秒" if mins > 0 else f"{secs}秒"
                lines.append(f"{i}. {emoji}{name} | 消耗体力{cost} | 需{time_str} | 🐾 {reward}猫条")
            lines.append("\n输入 `/接取劳务 序号` 来承接任务喵~")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"/猫力资源市场 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("接取劳务")
    async def accept_labor(self, event: AstrMessageEvent):
        try:
            parts = event.message_str.split()
            if len(parts) < 2:
                yield event.plain_result("请指定任务序号，例如：/接取劳务 1")
                return
            try:
                index = int(parts[1])
            except ValueError:
                yield event.plain_result("序号必须是数字喵～")
                return

            user_id = event.get_sender_id()
            neko = await self.get_neko(user_id)
            if not neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            is_new_day, stamina = await self.reset_daily_stamina(user_id, neko)
            if is_new_day:
                neko["stamina"] = stamina

            await self.refresh_labor_hall()
            tasks = await self.labor_collection.find({"status": "available"}).to_list(length=self.config["LABOR_HALL_SIZE"])

            if index < 1 or index > len(tasks):
                yield event.plain_result("序号超出范围喵～请重新选择")
                return

            task = tasks[index - 1]
            if neko["stamina"] < task["cost"]:
                yield event.plain_result(
                    f"{neko['neko_name']} 体力不足喵～需要 {task['cost']} 体力，你只有 {neko['stamina']}"
                )
                return

            now = datetime.datetime.now(timezone.utc)
            end_time = now + timedelta(seconds=task["duration"])

            await self.collection.update_one(
                {"user_id": user_id},
                {"$inc": {"stamina": -task["cost"]}}
            )
            await self.labor_collection.update_one(
                {"_id": task["_id"]},
                {"$set": {
                    "status": "in_progress",
                    "worker_id": user_id,
                    "start_time": now,
                    "end_time": end_time
                }}
            )
            emoji = task.get("emoji", "🐾")
            name = task.get("name", "劳务")
            duration_str = f"{task['duration']//60}分{task['duration']%60}秒"
            yield event.plain_result(
                f"✅ {neko['neko_name']} 接取了 {emoji}{name}！消耗{task['cost']}体力，将在{duration_str}后自动完成，报酬：{task['reward']}猫条喵～"
            )
        except Exception as e:
            logger.error(f"/接取劳务 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("我的劳务")
    async def my_labor(self, event: AstrMessageEvent):
        try:
            user_id = event.get_sender_id()
            neko = await self.get_neko(user_id)
            if not neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            await self.auto_complete_tasks(user_id)
            tasks = await self.labor_collection.find(
                {"worker_id": user_id, "status": "in_progress"}
            ).to_list(length=10)

            if not tasks:
                yield event.plain_result(f"{neko['neko_name']} 当前没有进行中的劳务喵～（也可在 /仪表盘 中查看）")
                return

            lines = [f"🔧 {neko['neko_name']} 进行中的劳务"]
            for i, t in enumerate(tasks, 1):
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
                lines.append(f"{i}. {emoji}{name} | 消耗{cost}体力 | 🐾{reward}猫条 | 剩余：{remaining_str}")
            lines.append("\n输入 `/取消劳务 序号` 可以取消（体力不返还）")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"/我的劳务 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("取消劳务")
    async def cancel_labor(self, event: AstrMessageEvent):
        try:
            parts = event.message_str.split()
            if len(parts) < 2:
                yield event.plain_result("请指定任务序号，例如：/取消劳务 1")
                return
            try:
                index = int(parts[1])
            except ValueError:
                yield event.plain_result("序号必须是数字喵～")
                return

            user_id = event.get_sender_id()
            neko = await self.get_neko(user_id)
            if not neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            tasks = await self.labor_collection.find(
                {"worker_id": user_id, "status": "in_progress"}
            ).to_list(length=10)

            if not tasks:
                yield event.plain_result(f"{neko['neko_name']} 当前没有进行中的劳务喵～")
                return

            if index < 1 or index > len(tasks):
                yield event.plain_result("序号超出范围喵～")
                return

            task = tasks[index - 1]
            await self.labor_collection.update_one(
                {"_id": task["_id"]},
                {"$set": {"status": "available"},
                 "$unset": {"worker_id": "", "start_time": "", "end_time": ""}}
            )
            yield event.plain_result(f"{neko['neko_name']} 已取消劳务，消耗的体力不会返还喵～")
        except Exception as e:
            logger.error(f"/取消劳务 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("你能做什么")
    async def help(self, event: AstrMessageEvent):
        help_text = f"""🐱 **Neko_Han 猫娘养成系统帮助**

👋 基础互动
  • `/喵` — 让 Neko_Han 和你打个招呼
  • `/你是猫娘么` — 问它是不是猫娘

🐈 猫娘养成
  • `/创建猫娘 <名字>` — 创建属于你的猫娘（名字须无空格）
  • `/修改名字 <新名字>` — 修改你的猫娘名字
  • `/仪表盘` — 查看猫娘状态（名字、猫条、体力、婚恋、劳务、决斗邀请）

💰 经济系统
  • `/签到` — 每日签到，随机获得 {self.config['SIGN_REWARD_MIN']}~{self.config['SIGN_REWARD_MAX']} 猫条
  • `/转账 <猫娘名字> <数量>` — 向其他猫娘转账猫条

🏗️ 劳动系统
  • `/猫力资源市场` — 查看可接劳务任务（每小时刷新）
  • `/接取劳务 <序号>` — 接取任务，消耗体力，完成后得猫条
  • `/我的劳务` — 查看进行中的任务
  • `/取消劳务 <序号>` — 取消任务（体力不返还）

💕 婚恋系统
  • `/求婚 <猫娘名字>` — 让你的猫娘向其他猫娘求婚
  • `/接受求婚 <猫娘名字>` — 接受对方的求婚
  • `/离婚` — 与当前配偶离婚

⚔️ 决斗系统
  • `/决斗 <猫娘名字> <赌注> <你的猜测>` — 向其他猫娘发起决斗
  • `/接受决斗 <发起者猫娘名字> <你的猜测>` — 应战
  • `/拒绝决斗 <发起者猫娘名字>` — 拒绝决斗
  • `/决斗列表` — 查看收到的决斗邀请

❓ 帮助
  • `/你能做什么` — 显示本帮助信息

💡 提示：所有猫娘关系通过用户 ID 绑定，体力每日重置，劳动大厅每小时刷新喵~"""
        yield event.plain_result(help_text)

    async def terminate(self):
        self.client.close()