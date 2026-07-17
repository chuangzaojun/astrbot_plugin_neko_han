import traceback
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import motor.motor_asyncio

@register("neko_han", "Neko_Han", "喵喵喵", "0.3")
class NekoHan(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
        self.db = self.client["neko-han"]
        self.collection = self.db["nekoes"]

    async def initialize(self):
        """初始化检查数据库连接"""
        try:
            await self.client.admin.command("ping")
            logger.info("数据库连接成功")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")

    @filter.command("喵")
    async def miao(self, event: AstrMessageEvent):
        """打招呼"""
        try:
            user_id = event.get_sender_id()
            chain = [Comp.At(qq=user_id), Comp.Plain("喵喵喵～我是由 Stalyx（创造君）开发的聊天机器人 Neko_Han 喵～")]
            yield event.chain_result(chain)
        except Exception as e:
            logger.error(f"指令 /喵 执行错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("你是猫娘么")
    async def are_you_neko(self, event: AstrMessageEvent):
        yield event.plain_result("是的喵～")

    @filter.command("创建猫娘")
    async def create_neko(self, event: AstrMessageEvent):
        """创建猫娘"""
        try:
            args = event.message_str.split()[1:]
            if len(args) != 1:
                yield event.plain_result("参数错误，需要一个无空格字符串作为猫娘名字")
                return
            user_id = event.get_sender_id()
            neko_name = args[0]

            if await self.collection.find_one({"user_id": user_id}) is not None:
                yield event.plain_result("你已经有猫娘了，不能重复创建喵～")
                return
            if await self.collection.find_one({"neko_name": neko_name}) is not None:
                yield event.plain_result("猫娘名字已经被占用，请换个名字喵～")
                return

            await self.collection.insert_one({"user_id": user_id, "neko_name": neko_name})
            yield event.plain_result(f"{neko_name} 现在是你的猫娘喵～")
        except Exception as e:
            logger.error(f"/创建猫娘 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("求婚")
    async def propose_marriage(self, event: AstrMessageEvent):
        """向其他用户的猫娘求婚"""
        try:
            args = event.message_str.split()[1:]
            if len(args) != 1:
                yield event.plain_result("参数错误，需要一个无空格字符串作为求婚对象的名字")
                return
            user_id = event.get_sender_id()
            target_name = args[0]

            my_neko = await self.collection.find_one({"user_id": user_id})
            if my_neko is None:
                yield event.plain_result("请先创建你的猫娘喵～")
                return
            if my_neko.get("wife") is not None:
                yield event.plain_result(f"你的猫娘 {my_neko['neko_name']} 已经有配偶了，不能求婚喵～")
                return

            target_neko = await self.collection.find_one({"neko_name": target_name})
            if target_neko is None:
                yield event.plain_result("找不到名为该名称的猫娘喵～")
                return

            # 存储对方的 user_id 而非名字
            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"proposing_to": target_neko["user_id"]}}
            )
            yield event.plain_result(f"{my_neko['neko_name']} 正在向 {target_neko['neko_name']} 求婚，等待对方同意喵～")
        except Exception as e:
            logger.error(f"/求婚 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("接受求婚")
    async def accept_marriage(self, event: AstrMessageEvent):
        """接受来自指定猫娘的求婚"""
        try:
            args = event.message_str.split()[1:]
            if len(args) != 1:
                yield event.plain_result("参数错误，需要一个无空格字符串作为求婚对象的名字")
                return
            user_id = event.get_sender_id()
            target_name = args[0]

            my_neko = await self.collection.find_one({"user_id": user_id})
            if my_neko is None:
                yield event.plain_result("请先创建你的猫娘喵～")
                return
            if my_neko.get("wife") is not None:
                yield event.plain_result(f"你的猫娘 {my_neko['neko_name']} 已经有配偶了，不能再接受求婚喵～")
                return

            # 找到求婚者猫娘（名字匹配且求婚对象是自己）
            proposer_neko = await self.collection.find_one({
                "neko_name": target_name,
                "proposing_to": user_id
            })
            if proposer_neko is None:
                yield event.plain_result("未找到来自该猫娘的有效求婚请求喵～")
                return

            # 互相设置配偶 user_id
            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"wife": proposer_neko["user_id"]}}
            )
            await self.collection.update_one(
                {"user_id": proposer_neko["user_id"]},
                {"$set": {"wife": user_id}, "$unset": {"proposing_to": ""}}
            )
            yield event.plain_result(f"{my_neko['neko_name']} x {proposer_neko['neko_name']} 百年好合喵～")
        except Exception as e:
            logger.error(f"/接受求婚 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    @filter.command("离婚")
    async def divorce(self, event: AstrMessageEvent):
        """与当前配偶离婚"""
        try:
            user_id = event.get_sender_id()
            my_neko = await self.collection.find_one({"user_id": user_id})
            if my_neko is None:
                yield event.plain_result("请先创建你的猫娘喵～")
                return

            partner_id = my_neko.get("wife")
            if partner_id is None:
                yield event.plain_result("你的猫娘目前单身喵～")
                return

            # 清除自己的配偶
            await self.collection.update_one(
                {"user_id": user_id},
                {"$unset": {"wife": ""}}
            )

            # 尝试清除对方的配偶
            result = await self.collection.update_one(
                {"user_id": partner_id},
                {"$unset": {"wife": ""}}
            )

            partner_neko = await self.collection.find_one({"user_id": partner_id})
            partner_display = partner_neko["neko_name"] if partner_neko else "未知猫娘"
            if result.modified_count == 0:
                yield event.plain_result(f"{my_neko['neko_name']} 和 {partner_display} 离婚成功，但对方可能已消失喵～")
            else:
                yield event.plain_result(f"{my_neko['neko_name']} 和 {partner_display} 离婚了喵～")
        except Exception as e:
            logger.error(f"/离婚 错误:\n{traceback.format_exc()}")
            yield event.plain_result("喵～服务器好像出了一点小问题，等等再试试喵~")

    async def terminate(self):
        """清理数据库连接"""
        self.client.close()