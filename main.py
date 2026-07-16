from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import motor.motor_asyncio

@register("neko_han", "Neko_Han", "喵喵喵", "0.1")
class NekoHan(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
        self.db = self.client["neko-han"]
        self.collection = self.db["nekoes"]

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("喵")
    async def miao(self, event: AstrMessageEvent):
        """向用户介绍自己""" # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        user_id = event.get_sender_id()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        chain = [
            Comp.At(qq=user_id),
            Comp.Plain('喵喵喵～我是由 Stalyx（创造君）开发的聊天机器人 Neko_Han 喵～')
        ]
        yield event.chain_result(chain)

    @filter.command("你是猫娘么")
    async def are_you_neko(self, event: AstrMessageEvent):
        yield event.plain_result("是的喵～")

    @filter.command("创建猫娘")
    async def create_neko(self, event: AstrMessageEvent):
        """创建自己的猫娘"""
        params = event.message_str.split()
        params.pop(0)
        if len(params) != 1:
            yield event.plain_result('参数错误，需要一个无空格字符串作为猫娘名字')
            return
        user_id = event.get_sender_id()
        neko_name = params[0]
        if await self.collection.find_one({"user_id": user_id}) != None:
            yield event.plain_result('已有猫娘，无法重复创建')
            return
        if await self.collection.find_one({"neko_name": neko_name}) != None:
            yield event.plain_result('猫娘名字与别人的重复，请换个名字喵')
            return
        await self.collection.insert_one({"user_id": user_id, "neko_name": neko_name})
        yield event.plain_result(neko_name+' 现在是你的喵～')

    @filter.command("求婚")
    async def propose_marriage(self, event: AstrMessageEvent):
        """向其他猫娘求婚"""
        params = event.message_str.split()
        params.pop(0)
        if len(params) != 1:
            yield event.plain_result('参数错误，需要一个无空格字符串作为求婚对象')
            return
        user_id = event.get_sender_id()
        proposing_name = params[0]
        my_neko_info = await self.collection.find_one({"user_id": user_id})
        proposing_neko_info = await self.collection.find_one({"neko_name": proposing_name})
        if proposing_neko_info is None:
            yield event.plain_result('未找到求婚对象')
            return
        await self.collection.update_one(my_neko_info, { "$set": {"proposing_name": proposing_neko_info["neko_name"]} })
        yield event.plain_result(my_neko_info["neko_name"] + ' 正在向 ' + proposing_neko_info["neko_name"] + ' 求婚喵，等待对方同意喵')

    @filter.command("接受求婚")
    async def accept_marriage(self, event: AstrMessageEvent):
        """接受其他猫娘求婚"""
        params = event.message_str.split()
        params.pop(0)
        if len(params) != 1:
            yield event.plain_result('参数错误，需要一个无空格字符串作为接受求婚对象')
            return
        user_id = event.get_sender_id()
        proposing_name = params[0]
        my_neko_info = await self.collection.find_one({"user_id": user_id})
        if my_neko_info is None:
            yield event.plain_result('请先创建你的猫娘')
            return
        proposing_neko_info = await self.collection.find_one({"neko_name": proposing_name})
        if (proposing_neko_info is None) or (proposing_neko_info.get("proposing_name") != my_neko_info["neko_name"]):
            yield event.plain_result('未找到求婚对象')
            return
        await self.collection.update_one(my_neko_info, { "$set": {"wife": proposing_neko_info["neko_name"]} })
        await self.collection.update_one(proposing_neko_info, { "$set": {"wife": my_neko_info["neko_name"]} })
        await self.collection.update_one(proposing_neko_info, { "$unset": {"proposing_name": ""} })
        yield event.plain_result(my_neko_info["neko_name"] + ' x ' + proposing_neko_info["neko_name"] + ' 百年好合喵')

    @filter.command("离婚")
    async def divorce(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        my_neko_info = await self.collection.find_one({"user_id": user_id})
        if my_neko_info is None:
            yield event.plain_result('请先创建你的猫娘')
            return
        if my_neko_info.get("wife") is None:
            yield event.plain_result('你的猫娘单身喵')
            return
        wife_name = my_neko_info["wife"]
        wife_info = await self.collection.find_one({"neko_name" :wife_name})
        await self.collection.update_one(my_neko_info, { "$unset": {"wife": ""} })
        await self.collection.update_one(wife_info, { "$unset": {"wife": ""} })
        yield event.plain_result(my_neko_info["neko_name"] + " 和 " + wife_name + " 离婚喵")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
