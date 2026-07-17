import traceback
import random
import datetime
from datetime import timezone, timedelta
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
from .const import LABOR_HALL_SIZE, REFRESH_INTERVAL, DEFAULT_STAMINA, LABOR_TASKS

class LaborMixin:
    """劳务系统：市场刷新、接取、查看、取消"""

    # refresh_labor_hall 和 auto_complete_tasks 被仪表盘和劳务市场共用
    async def refresh_labor_hall(self):
        now = datetime.datetime.now(timezone.utc)
        if self.last_refresh_time and (now - self.last_refresh_time).total_seconds() < REFRESH_INTERVAL:
            return

        await self.labor_collection.delete_many({"status": {"$ne": "in_progress"}})

        new_tasks = []
        for _ in range(LABOR_HALL_SIZE):
            cost = random.randint(50, 200)
            duration = random.randint(5 * 60, 30 * 60)  # 5~30分钟（秒）
            reward = cost * 2 + random.randint(0, cost // 2)
            task_desc = random.choice(LABOR_TASKS)
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

    @filter.command("猫力资源市场")
    async def labor_hall(self, event: AstrMessageEvent):
        try:
            user_id = event.get_sender_id()
            neko = await self.get_neko(user_id)
            if not neko:
                yield event.plain_result("你还没有猫娘，请先创建一只喵～")
                return

            await self.refresh_labor_hall()
            tasks = await self.labor_collection.find({"status": "available"}).to_list(length=LABOR_HALL_SIZE)

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
            tasks = await self.labor_collection.find({"status": "available"}).to_list(length=LABOR_HALL_SIZE)

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