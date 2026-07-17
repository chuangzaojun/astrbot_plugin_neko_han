import traceback
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger

class MarriageMixin:
    """婚恋系统：求婚、接受求婚、离婚"""

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