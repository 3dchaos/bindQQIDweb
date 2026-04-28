import json
import asyncio
import websockets
import re
import dataset
import datetime
import sys
import os
import binascii
from Crypto.Cipher import DES
from data_manager import read_file_data, write_file_data
from config import DB_URL

class BotWorker:
    def __init__(self, ws_url, max_binds, log_func, get_filepath_func):
        self.ws_url = ws_url
        self.max_binds = max_binds
        self.log_func = log_func
        self.get_filepath = get_filepath_func
        
        # 界面控制开关
        self.enable_group_manage = False
        self.enable_checkin = False
        self.enable_patrol = False 
        self.enable_auto_join = False # 自动进群开关
        self.enable_decoder = False # 新增：解码器开关
        self.enable_decoder_group = "" # 新增：指定监听解码的群号
        self.running = False
        self.loop = None
        
        # API 异步请求字典
        self.pending_requests = {}
        self.request_id_counter = 0

    async def call_api(self, websocket, action, params):
        self.request_id_counter += 1
        echo_id = str(self.request_id_counter)
        future = self.loop.create_future()
        self.pending_requests[echo_id] = future
        
        payload = {"action": action, "params": params, "echo": echo_id}
        await websocket.send(json.dumps(payload))
        
        try:
            result = await asyncio.wait_for(future, timeout=3.0)
            if result.get("status") == "failed": return None
            return result.get("data")
        except asyncio.TimeoutError:
            self.pending_requests.pop(echo_id, None)
            return None

    async def send_private_msg(self, websocket, user_id, text):
        await websocket.send(json.dumps({"action": "send_private_msg", "params": {"user_id": user_id, "message": text}}))

    async def send_group_msg(self, websocket, group_id, text):
        await websocket.send(json.dumps({"action": "send_group_msg", "params": {"group_id": group_id, "message": text}}))

    
    # --- [辅助方法] 生成通用的开区列表回复文本 ---
    def get_zones_msg(self, zones, records):
        counts = {z: 0 for z in zones}
        for r in records:
            try:
                # 记录格式: account:zone|qq|nickname
                acc_zone = r.split('|')[0]
                zone = acc_zone.split(':')[1]
                if zone in counts: counts[zone] += 1
            except: pass
        
        reply = "【🏰 当前开区列表及注册人数】\n"
        if not zones:
            reply += "暂无开区信息。"
        else:
            for z in zones:
                reply += f"🔹 {z} ：{counts.get(z, 0)} 人已注册\n"
        return reply.strip()

    def load_decoder_config(self):
        """加载解码器配置"""
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        config_file = os.path.join(base_path, "auth_config.json")
        try:
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            self.log_func(f"❌ 读取解码器配置失败: {e}")
        return {"versions": {}}

    def generate_auth_code(self, machine_code, des_key):
        """生成授权码"""
        try:
            clean_code = machine_code.upper()
            cipher = DES.new(des_key.encode('utf-8'), DES.MODE_ECB)
            data = clean_code.ljust(16)[:16].encode('utf-8')
            encrypted = cipher.encrypt(data)
            return binascii.hexlify(encrypted).decode().upper()
        except Exception as e:
            self.log_func(f"❌ 生成授权码失败: {e}")
            return None

    # --- 处理私聊消息 (自动附带列表版) ---
    async def handle_private_message(self, websocket, data):
        sender = data.get("sender", {})
        qq_num = sender.get("user_id")
        nickname = sender.get("nickname", "未知昵称")
        msg_text = data.get("raw_message", "").strip()

        filepath = self.get_filepath()
        zones, records = read_file_data(filepath)

        # 1. 指令：开区列表
        if msg_text == "开区列表":
            reply = self.get_zones_msg(zones, records)
            await self.send_private_msg(websocket, qq_num, reply)
            return
        # 过滤卡片消息，防止触发“无法识别”回复
        if "[卡片]" in msg_text or msg_text.startswith('{"app"') or "[CQ:json" in msg_text:
            self.log_func(f"收到私聊邀请卡片 (来自QQ:{qq_num})，已跳过自动回复。")
            return
        # 2. 指令：查下名下账号
        if msg_text == "查下名下账号":
            found = []
            for r in records:
                try:
                    parts = r.split('|')
                    if len(parts) >= 2 and parts[1] == str(qq_num):
                        acc_zone = parts[0]
                        acc, zone = acc_zone.split(':')
                        found.append(f"账号：{acc} ({zone})")
                except: pass
            reply = "【👤 您名下已绑定账号】\n" + ("\n".join(found) if found else "未查询到记录")
            await self.send_private_msg(websocket, qq_num, reply)
            return

        # 3. 绑定指令匹配
        bind_match = re.search(r"绑定\s*(\S+)\s*(?:账号[:：]?)?\s*(\S+)", msg_text)
        
        if bind_match:
            zone_name = re.sub(r"[,，:：\-\s]", "", bind_match.group(1).strip())
            account = re.sub(r"[,，:：\-\s]", "", bind_match.group(2).strip())
            
            # 获取公共列表，准备在失败时使用
            zones_list_txt = self.get_zones_msg(zones, records)

            # 校验区服是否存在
            if zone_name not in zones:
                fail_msg = f"❌ 注册失败：【{zone_name}】不在开区名单内！\n\n{zones_list_txt}"
                await self.send_private_msg(websocket, qq_num, fail_msg)
                return

            # 校验是否已被注册
            my_binds = 0
            account_registered = False
            for r in records:
                try:
                    p = r.split('|')
                    if p[0] == f"{account}:{zone_name}": account_registered = True
                    if p[1] == str(qq_num): my_binds += 1
                except: continue

            if account_registered:
                fail_msg = f"❌ 注册失败：账号【{account}】在【{zone_name}】已被占用！\n\n{zones_list_txt}"
                await self.send_private_msg(websocket, qq_num, fail_msg)
                return

            # 校验次数上限
            if my_binds >= self.max_binds:
                fail_msg = f"❌ 注册失败：您在此区的名额已满({self.max_binds}个)！\n\n{zones_list_txt}"
                await self.send_private_msg(websocket, qq_num, fail_msg)
                return

            # 最终写入
            new_record = f"{account}:{zone_name}|{qq_num}|{nickname}"
            records.append(new_record)
            if write_file_data(filepath, zones, records):
                success_msg = f"🎉 绑定成功！\n区服：{zone_name}\n账号：{account}\n祝您游戏愉快！"
                await self.send_private_msg(websocket, qq_num, success_msg)
                self.log_func(f"✅ 私聊绑定成功: {new_record}")
            return

        # 4. 兜底回复
        default_reply = (
            "🤖 无法识别指令。请尝试：\n"
            "绑定 区号 游戏账号 (例如:绑定 热血传奇二区 qwe123asd)\n"
            "开区列表\n"
            "查下名下账号"
        )
        await self.send_private_msg(websocket, qq_num, default_reply)

    async def handle_group_increase(self, websocket, data):
        if not self.enable_patrol: return
        group_id = data.get("group_id")
        user_id = str(data.get("user_id"))
        self_id = data.get("self_id")

        if str(user_id) == str(self_id): return 

        if self.table_blacklist.find_one(group_id=group_id, user_id=user_id):
            self.log_func(f"🚨 巡逻触发: 发现黑名单成员 {user_id} 加入群 {group_id}，正在拦截...")
            
            is_bot_admin = False
            bot_admin_record = self.table_bot_admin.find_one(group_id=group_id)
            if bot_admin_record is not None:
                is_bot_admin = bot_admin_record['is_admin']
            else:
                bot_info = await self.call_api(websocket, "get_group_member_info", {"group_id": group_id, "user_id": self_id, "no_cache": True})
                if bot_info:
                    bot_role = bot_info.get("role", "member")
                    is_bot_admin = bot_role in ["owner", "admin"]
                    self.table_bot_admin.upsert(dict(group_id=group_id, is_admin=is_bot_admin), ["group_id"])

            if is_bot_admin:
                await self.call_api(websocket, "set_group_kick", {"group_id": group_id, "user_id": int(user_id), "reject_add_request": False})
                await self.send_group_msg(websocket, group_id, f"{user_id}为本群黑名单，已将他踢出群。")
                self.log_func(f"✅ 巡逻踢黑成功: 已自动清退成员 {user_id}")
            else:
                self.log_func(f"❌ 巡逻踢黑失败: 机器人在群 {group_id} 没有管理员权限。")

    async def handle_group_message(self, websocket, data):
        if not self.enable_group_manage and not self.enable_decoder: return

        group_id = data.get("group_id")
        sender = data.get("sender", {})
        user_id = sender.get("user_id")
        nickname = sender.get("nickname", "未知昵称")
        role = sender.get("role", "member")
        raw_msg = data.get("raw_message", "").strip()
        self_id = data.get("self_id")

        clean_msg = re.sub(rf"\[CQ:at,qq={self_id}(,name=[^\]]+)?\]\s*", "", raw_msg).strip()

        cmd_type = ""
        target_qq = ""
        cmd_params = {}

        # 仅在开启群管理时处理管理指令
        if self.enable_group_manage:
            if re.match(r"^/?(?:加入黑名单QQ|加黑)(?:\s+(.*))?$", clean_msg):
                cmd_type = "add_black"
                m = re.match(r"^/?(?:加入黑名单QQ|加黑)(?:\s+(.*))?$", clean_msg)
                val = m.group(1).strip() if m.group(1) else ""
                if not val or not val.isdigit():
                    await self.send_group_msg(websocket, group_id, "❌ 格式错误！\n正确格式：加黑 [QQ号]\n例如：加黑 123456")
                    return
                target_qq = val
            elif re.match(r"^/?(?:删除黑名单QQ|删黑)(?:\s+(.*))?$", clean_msg):
                cmd_type = "del_black"
                m = re.match(r"^/?(?:删除黑名单QQ|删黑)(?:\s+(.*))?$", clean_msg)
                val = m.group(1).strip() if m.group(1) else ""
                if not val or not val.isdigit():
                    await self.send_group_msg(websocket, group_id, "❌ 格式错误！\n正确格式：删黑 [QQ号]\n例如：删黑 123456")
                    return
                target_qq = val
            elif clean_msg in ["黑名单QQ", "黑名单", "黑", "/黑名单QQ", "/黑名单", "/黑"]:
                cmd_type = "list_black"
            elif clean_msg in ["功能", "/功能"]:
                cmd_type = "menu"
            elif clean_msg in ["签到", "/签到"]:
                cmd_type = "checkin"
            elif clean_msg in ["积分", "/积分"]:
                cmd_type = "points"
            elif re.match(r"^/?新增SDK(?:\s+(.*))?$", clean_msg):
                cmd_type = "add_sdk"
                m = re.match(r"^新增SDK(?:\s+(.*))?$", clean_msg)
                params_str = m.group(1).strip() if m.group(1) else ""
                parts = params_str.split()
                
                if len(parts) != 2:
                    await self.send_group_msg(websocket, group_id, "❌ 新增失败：参数不齐！\n正确格式：新增SDK [数量] [价格]\n例如：新增SDK 10 50")
                    return

                try:
                    qty = int(parts[0])
                    price = int(parts[1])
                except ValueError:
                    await self.send_group_msg(websocket, group_id, "❌ 新增失败：数量和价格必须为整数！")
                    return

                if qty < 1 or qty > 100:
                    await self.send_group_msg(websocket, group_id, "❌ 新增失败：单次新增数量范围为 1-100！")
                    return
                
                if price < 0:
                    await self.send_group_msg(websocket, group_id, "❌ 新增失败：价格不能为负数！")
                    return

                cmd_params = {}
                cmd_params['qty'] = qty
                cmd_params['price'] = price
            elif clean_msg == "查询所有SDK":
                cmd_type = "list_sdk"
            elif re.match(r"^购买SDK(?:\s+(\d+))?(?:积分)?$", clean_msg):
                cmd_type = "buy_sdk"
            elif clean_msg == "删除所有SDK":
                cmd_type = "clear_sdk"

        # 判断是否为解码器相关消息 (增加群号过滤)
        is_decoder_msg = False
        if self.enable_decoder:
            # 如果设置了监听群号，则只在该群响应
            target_group = str(self.enable_decoder_group).strip()
            if not target_group or str(group_id) == target_group:
                if "授权凭证" in clean_msg or re.search(r"(?:机器识别码|机器码)", clean_msg, re.I):
                    is_decoder_msg = True

        if not cmd_type and not is_decoder_msg: return

        # 1. 验证【机器人本身】是否为管理员
        is_bot_admin = False
        bot_admin_record = self.table_bot_admin.find_one(group_id=group_id)
        if bot_admin_record is not None:
            is_bot_admin = bot_admin_record['is_admin']
        else:
            bot_info = await self.call_api(websocket, "get_group_member_info", {"group_id": group_id, "user_id": self_id, "no_cache": True})
            if bot_info:
                bot_role = bot_info.get("role", "member")
                is_bot_admin = bot_role in ["owner", "admin"]
                self.table_bot_admin.upsert(dict(group_id=group_id, is_admin=is_bot_admin), ["group_id"])
            
        if not is_bot_admin:
            # 只有是明确的指令或触发词时才提示，避免干扰日常聊天
            await self.send_group_msg(websocket, group_id, "⚠️ 抱歉，本机器人必须拥有【群主/管理员】权限，才能在此群开启功能哦~")
            return

        # --- [新增] 解码器功能处理 ---
        if is_decoder_msg:
            # 1. 指令触发说明
            if "授权凭证" in clean_msg:
                config = self.load_decoder_config()
                versions = config.get("versions", {})
                if not versions:
                    await self.send_group_msg(websocket, group_id, "⚠️ 解码器已开启，但未找到有效的版本配置(auth_config.json)。")
                else:
                    v_list_str = "、".join(versions.keys())
                    reply = (
                        f"【🤖 授权解码服务已启动】\n"
                        f"当前支持版本：{v_list_str}\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"请按以下格式发送（兼容空格）：\n"
                        f"机器识别码：XXXXXXXX 解码版本：XXX\n"
                        f"例如：机器识别码：123456ABCDEF 黑不溜秋"
                    )
                    await self.send_group_msg(websocket, group_id, reply)
                return

            # 2. 匹配解码请求 (机器识别码/机器码)
            decoder_match = re.search(r"(?:机器识别码|机器码)[:：\s]*([a-zA-Z0-9]+)", clean_msg, re.I)
            if decoder_match:
                machine_code = decoder_match.group(1)
                config = self.load_decoder_config()
                versions = config.get("versions", {})
                
                matched_version = None
                matched_key = None
                for v_name, v_key in versions.items():
                    if v_name in clean_msg:
                        matched_version = v_name
                        matched_key = v_key
                        break
                
                if matched_version and matched_key:
                    auth_code = self.generate_auth_code(machine_code, matched_key)
                    if auth_code:
                        # 私聊发送
                        result_msg = (
                            f"✅ 授权码生成成功！\n"
                            f"━━━━━━━━━━━━━━\n"
                            f"👉 使用版本：{matched_version}\n"
                            f"👉 客户机器码：{machine_code.upper()}\n"
                            f"🔑 解锁授权码：{auth_code}\n"
                            f"━━━━━━━━━━━━━━"
                        )
                        await self.send_private_msg(websocket, user_id, result_msg)
                        # 群内反馈
                        await self.send_group_msg(websocket, group_id, f"✅ [CQ:at,qq={user_id}] 授权码已通过【私聊】发送，请注意查收。")
                        self.log_func(f"✅ 解码成功: {user_id} | 版本: {matched_version}")
                    return
        # --- [解码器结束] ---

        if not cmd_type: return

        # 2. 权限验证
        is_owner = role == "owner"
        is_admin = role in ["owner", "admin"]

        if cmd_type in ["add_sdk", "clear_sdk"]:
            if not is_owner:
                await self.send_group_msg(websocket, group_id, f"🚫 [CQ:at,qq={user_id}] 权限不足！该指令仅限【群主】使用。")
                return
        elif cmd_type in ["del_black", "add_black", "list_black"]:
            if not is_admin:
                self.log_func(f"🚫 拦截: 成员 {user_id} 并非管理，无权操作此指令。")
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 权限不足！需要您是本群的群主或管理员！")
                return

        # ================ 路由 ================
        if cmd_type == "menu":
            # 动态读取本群未使用的SDK价格
            sdks_in_db = list(self.table_sdk.find(group_id=group_id, is_used=0))
            price_stats = {}
            for s in sdks_in_db:
                p = s['price']
                price_stats[p] = price_stats.get(p, 0) + 1
            
            sdk_info = ""
            if not price_stats:
                sdk_info = " (暂无可用SDK)"
            else:
                prices_str = "/".join([f"{p}积分" for p in sorted(price_stats.keys())])
                sdk_info = f" ({prices_str})"

            reply = (
                "【🛠️ 机器人功能菜单】\n"
                "签到 (获得1积分)\n"
                "积分 (查看个人积分)\n"
                f"购买SDK{sdk_info}\n"
                "--- 管理员指令 ---\n"
                "查询所有SDK (仅限管理)\n"
                "新增SDK 数量 价格 (仅限群主)\n"
                "删除所有SDK (仅限群主)\n"
                "黑名单QQ (查看列表)\n"
                "加黑 QQ (拉黑)\n"
                "删黑 QQ (移出)"
            )
            await self.send_group_msg(websocket, group_id, reply)
            
        elif cmd_type == "add_sdk":
            import random
            import string
            
            qty = cmd_params['qty']
            price = cmd_params['price']
            
            # 检查当前数据库总量
            current_total = self.table_sdk.count(group_id=group_id)
            if current_total + qty > 100:
                available = 100 - current_total
                await self.send_group_msg(websocket, group_id, 
                    f"❌ 新增失败：本群 SDK 总容量上限为 100 条。\n"
                    f"当前已存在：{current_total} 条\n"
                    f"本次尝试新增：{qty} 条\n"
                    f"剩余空间：{max(0, available)} 条\n"
                    f"💡 请先执行【删除所有SDK】后再批量新增。")
                return

            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            success_count = 0
            for _ in range(qty):
                random_sdk = ''.join(random.choices(string.digits, k=13))
                try:
                    self.table_sdk.insert(dict(
                        group_id=group_id,
                        sdk=random_sdk,
                        is_used=0,
                        price=price,
                        buyer=None,
                        create_time=now_str,
                        buy_time=None
                    ))
                    success_count += 1
                except Exception as e:
                    self.log_func(f"❌ 数据库写入失败: {e}")

            await self.send_group_msg(websocket, group_id, 
                f"✅ SDK 生成成功！\n群号：{group_id}\n新增数量：{success_count}\n单价：{price} 积分\n时间：{now_str}")

        elif clean_msg == "查询所有SDK":
            if not is_admin:
                await self.send_group_msg(websocket, group_id, f"🚫 [CQ:at,qq={user_id}] 权限不足！该指令仅限【管理】使用。")
                return
            
            all_sdks = list(self.table_sdk.find(group_id=group_id))
            if not all_sdks:
                await self.send_group_msg(websocket, group_id, "❌ 查询失败：本群数据库中暂无 SDK 记录。")
                return

            lines = [f"【📋 群 {group_id} SDK 全量列表】", "━━━━━━━━━━━━━━"]
            for s in all_sdks:
                status = "🔴 已使用" if s['is_used'] else "🟢 未使用"
                buyer_info = f" | 购买人: {s['buyer']}" if s['buyer'] else ""
                lines.append(f"🔑 SDK: {s['sdk']}\n💰 价格: {s['price']} | 状态: {status}{buyer_info}")
                lines.append("--------------")
            
            full_msg = "\n".join(lines)
            await self.send_private_msg(websocket, user_id, full_msg)
            await self.send_group_msg(websocket, group_id, f"✅ 已将本群所有 SDK 记录({len(all_sdks)}条)私聊发送给管理。")

        elif re.match(r"^购买SDK(?:\s+(\d+))?$", clean_msg):
            # 获取本群所有未使用的SDK价格
            available_sdks = list(self.table_sdk.find(group_id=group_id, is_used=0))
            if not available_sdks:
                await self.send_group_msg(websocket, group_id, "❌ 购买失败：当前仓库内暂无可用 SDK。")
                return

            distinct_prices = sorted(list(set([s['price'] for s in available_sdks])))
            
            m = re.match(r"^购买SDK(?:\s+(\d+))?$", clean_msg)
            input_price_str = m.group(1)
            
            target_price = None
            if input_price_str:
                target_price = int(input_price_str)
            else:
                if len(distinct_prices) == 1:
                    target_price = distinct_prices[0]
                else:
                    prices_list = "/".join([str(p) for p in distinct_prices])
                    await self.send_group_msg(websocket, group_id, f"💡 请输入具体的购买价格，例如：购买SDK {distinct_prices[0]}\n当前可用价格：{prices_list}")
                    return

            # 校验该价格是否有库存
            sdk_record = self.table_sdk.find_one(group_id=group_id, price=target_price, is_used=0)
            if not sdk_record:
                await self.send_group_msg(websocket, group_id, f"❌ 购买失败：价格为 {target_price} 的 SDK 已售罄。")
                return
            
            # 校验积分
            user_record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not user_record or user_record['points'] < target_price:
                current_pts = user_record['points'] if user_record else 0
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] ❌ 积分不足！购买需 {target_price} 积分，你当前仅有 {current_pts} 积分。")
                return
            
            # 执行购买
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_points = user_record['points'] - target_price
            
            self.table_group.update(dict(id=user_record['id'], points=new_points), ['id'])
            self.table_sdk.update(dict(
                id=sdk_record['id'], 
                is_used=1, 
                buyer=user_id, 
                buy_time=now_str
            ), ['id'])
            
            # 私聊发送SDK给购买者
            private_msg = (
                f"🎉 购买成功！\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔑 您的 SDK：{sdk_record['sdk']}\n"
                f"💰 消耗积分：{target_price}\n"
                f"📅 购买时间：{now_str}\n"
                f"━━━━━━━━━━━━━━"
            )
            await self.send_private_msg(websocket, user_id, private_msg)
            
            # 群内提示
            await self.send_group_msg(websocket, group_id, f"🎉 [CQ:at,qq={user_id}] 购买成功！\n消耗积分：{target_price}\n密钥已通过【私聊】发送，请注意查收。")

        elif cmd_type == "clear_sdk":
            try:
                self.table_sdk.delete(group_id=group_id)
                await self.send_group_msg(websocket, group_id, "🧹 已成功清空本群所有 SDK 记录。")
                self.log_func(f"✅ SDK清空: 群 {group_id}")
            except Exception as e:
                await self.send_group_msg(websocket, group_id, f"❌ 清空失败：数据库操作异常。\n错误信息：{str(e)}")
                self.log_func(f"❌ SDK清空失败: {e}")

        elif cmd_type == "checkin":
            if not self.enable_checkin: return
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not record:
                self.table_group.insert(dict(group_id=group_id, user_nickname=nickname, user_id=user_id, points=1, last_checkin_date=today))
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到成功，积分+1")
            elif record['last_checkin_date'] == today:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到失败，今天已经签到过了~")
            else:
                self.table_group.update(dict(id=record['id'], points=record['points'] + 1, last_checkin_date=today, user_nickname=nickname), ['id'])
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到成功，积分+1")
                
        elif cmd_type == "points":
            if not self.enable_checkin: return
            record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not record:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 没有你的记录")
            else:
                pts = record['points']
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 你拥有积分是:{pts}，签到时间为：{record['last_checkin_date']}")

        elif cmd_type == "list_black":
            bl_records = list(self.table_blacklist.find(group_id=group_id))
            if not bl_records:
                await self.send_group_msg(websocket, group_id, "当前群的黑名单为空。")
            else:
                bl_qqs = [str(x['user_id']) for x in bl_records]
                await self.send_group_msg(websocket, group_id, f"当前群黑名单包含QQ: {', '.join(bl_qqs)}")

        elif cmd_type == "add_black" and target_qq:
            if not self.table_blacklist.find_one(group_id=group_id, user_id=target_qq):
                self.table_blacklist.insert(dict(group_id=group_id, user_id=target_qq))
                await self.send_group_msg(websocket, group_id, f"已将QQ {target_qq} 成功加入黑名单。")
                self.log_func(f"✅ 加入黑名单: {target_qq}")
                
                if self.enable_patrol:
                    await self.call_api(websocket, "set_group_kick", {"group_id": group_id, "user_id": int(target_qq), "reject_add_request": False})
            else:
                await self.send_group_msg(websocket, group_id, f"QQ {target_qq} 已经在黑名单列表中了。")

        elif cmd_type == "del_black" and target_qq:
            self.table_blacklist.delete(group_id=group_id, user_id=target_qq)
            await self.send_group_msg(websocket, group_id, f"已将QQ {target_qq} 移出黑名单。")
            self.log_func(f"✅ 移出黑名单: {target_qq}")



    async def handle_group_request(self, websocket, data):
        """处理加群请求/邀请"""
        if not self.enable_auto_join: return 

        if data.get("request_type") == "group" and data.get("sub_type") == "invite":
            group_id = data.get("group_id")
            self.log_func(f"🔔 发现群邀请：{group_id}，正在自动加入...")
            await self.call_api(websocket, "set_group_add_request", {
                "flag": data.get("flag"),
                "sub_type": "invite",
                "approve": True
            })



    async def start(self):
        self.running = True
        try:
            self.db = dataset.connect(DB_URL)
            self.table_group = self.db['QQgroup']
            self.table_blacklist = self.db['Blacklist']
            self.table_bot_admin = self.db['BotGroupAdmin']
            self.table_sdk = self.db['SDK']
            self.log_func("✅ 数据库加载成功")
        except Exception as e:
            self.log_func(f"❌ 数据库异常: {e}")
            return

        self.log_func(f"正在连接: {self.ws_url}")
        try:
            async with websockets.connect(self.ws_url) as websocket:
                self.log_func("✅ LLOneBot 连接成功！")
                while self.running:
                    try:
                        msg = await websocket.recv()
                        data = json.loads(msg)
                        
                        if "echo" in data:
                            echo_id = str(data["echo"])
                            if echo_id in self.pending_requests:
                                if not self.pending_requests[echo_id].done():
                                    self.pending_requests[echo_id].set_result(data)
                                del self.pending_requests[echo_id]
                            continue

                        if data.get("post_type") == "notice" and data.get("notice_type") == "group_increase":
                            asyncio.create_task(self.handle_group_increase(websocket, data))

                        elif data.get("post_type") == "notice" and data.get("notice_type") == "group_admin":
                            sub_type = data.get("sub_type")
                            group_id = data.get("group_id")
                            user_id = data.get("user_id")
                            if str(user_id) == str(data.get("self_id")):
                                is_admin = (sub_type == "set")
                                self.table_bot_admin.upsert(dict(group_id=group_id, is_admin=is_admin), ["group_id"])
                                status_txt = "提拔为" if is_admin else "取消了"
                                self.log_func(f"🔔 权限变动: 机器人在群 {group_id} 被{status_txt}管理权限")

                        elif data.get("post_type") == "message":
                            msg_type = data.get("message_type")
                            if msg_type == "private":
                                asyncio.create_task(self.handle_private_message(websocket, data))
                            elif msg_type == "group":
                                asyncio.create_task(self.handle_group_message(websocket, data))
                        
                        # 找到 post_type 判断区域，添加这个分支
                        elif data.get("post_type") == "request":
                            asyncio.create_task(self.handle_group_request(websocket, data))
                    except json.JSONDecodeError: pass
        except Exception as e:
            self.log_func(f"❌ 连接异常或断开: {e}")
        self.running = False