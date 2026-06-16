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
        self.max_cdk_binds = 5 # 新增：默认CDK上限
        self.max_group_cdk = 100 # 新增：默认群CDK容量
        self.log_func = log_func
        self.get_filepath = get_filepath_func
        
        # 界面控制开关
        self.enable_group_manage = False
        self.enable_checkin = False
        self.enable_patrol = False 
        self.enable_auto_join = False # 自动进群开关
        self.enable_decoder = False # 新增：解码器开关
        self.enable_decoder_group = "" # 新增：指定监听解码的群号
        self.enable_group_bind = False # 新增：群绑定开关
        self.enable_bind_group = "" # 新增：指定监听绑定的群号
        self.enable_auto_friend = False # 新增：自动同意好友开关
        self.enable_auto_recall = False # 新增：3秒撤回开关
        self.recall_delay = 3 # 新增：撤回延迟
        self.recall_cmds = [] # 新增：需要撤回的指令列表
        self.running = False
        self.loop = None
        
        # 游戏文本同步路径 (根据目录结构定位)
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.game_unused_file = os.path.join(self.base_dir, "Mir2Text", "典狱长功能", "未使用CDK.txt")
        self.game_used_log_file = os.path.join(self.base_dir, "Mir2Text", "典狱长功能", "已使用.txt")
        
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

    async def send_group_msg(self, websocket, group_id, text, cmd_type=None):
        # 使用 call_api 以获取 message_id 用于撤回
        data = await self.call_api(websocket, "send_group_msg", {"group_id": group_id, "message": text})
        
        should_recall = False
        if self.enable_auto_recall:
            if cmd_type in self.recall_cmds:
                should_recall = True
        
        if should_recall and data and "message_id" in data:
            message_id = data["message_id"]
            async def delayed_recall():
                await asyncio.sleep(self.recall_delay)
                await self.call_api(websocket, "delete_msg", {"message_id": message_id})
                self.log_func(f"🕒 已自动撤回机器人消息({cmd_type}): {message_id}")
            asyncio.create_task(delayed_recall())

    
    # --- [辅助方法] 生成通用的开区列表回复文本 ---
    def get_zones_msg(self, zones, records):
        counts = {z: 0 for z in zones}
        for r in records:
            try:
                # 记录格式: account:zone|qq|nickname
                acc_zone = r.split('|')[0]
                # 使用 rsplit 确保取到最后一个冒号后的区名，适配账号含冒号的情况
                zone = acc_zone.rsplit(':', 1)[-1]
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

        # [优化] 私聊回复过滤：仅当开启了“绑定”功能，且发送者是“绑定群”成员时才回复
        if not self.enable_group_bind:
            return

        target_bind_group = str(self.enable_bind_group).strip()
        if not target_bind_group:
            return

        try:
            # 尝试获取成员信息，校验是否在绑定群中
            member_info = await self.call_api(websocket, "get_group_member_info", {
                "group_id": int(target_bind_group),
                "user_id": int(qq_num),
                "no_cache": True
            })
            if not member_info:
                self.log_func(f"👤 私聊过滤: 用户 {qq_num} 不在绑定群 {target_bind_group} 中，已忽略消息。")
                return
        except Exception as e:
            # 如果查询异常（如群号格式错误或网络问题），为保险起见选择不回复
            self.log_func(f"⚠️ 私聊过滤校验异常: {e}")
            return
        
        # 优化昵称处理：处理缺失、过滤可能破坏格式的特殊字符
        raw_nickname = sender.get("nickname")
        if not raw_nickname:
            nickname = "无昵称"
        else:
            # 移除换行符、分隔符(|)和冒号(:)，防止破坏记录格式，并截断过长昵称
            nickname = re.sub(r"[\r\n|:]", " ", str(raw_nickname)).strip()
            if not nickname: nickname = "无昵称"
            nickname = nickname[:20] # 限制长度防止超长
            
        msg_text = data.get("raw_message", "").strip()

        filepath = self.get_filepath()
        zones, records = read_file_data(filepath)

        # 1. 指令：开区列表
        if re.fullmatch(r"开区列表", msg_text, re.I):
            reply = self.get_zones_msg(zones, records)
            await self.send_private_msg(websocket, qq_num, reply)
            return
        # 过滤卡片消息，防止触发“无法识别”回复
        if "[卡片]" in msg_text or msg_text.startswith('{"app"') or "[CQ:json" in msg_text:
            self.log_func(f"收到私聊邀请卡片 (来自QQ:{qq_num})，已跳过自动回复。")
            return
        # 2. 指令：查下名下账号
        if re.fullmatch(r"(?:查下名下账号|查账号|我的账号)", msg_text, re.I):
            found = []
            for r in records:
                try:
                    parts = r.split('|')
                    if len(parts) >= 2 and parts[1] == str(qq_num):
                        acc_zone = parts[0]
                        # 使用 rsplit 适配账号含冒号的情况
                        acc, zone = acc_zone.rsplit(':', 1)
                        found.append(f"账号：{acc} ({zone})")
                except: pass
            reply = "【👤 您名下已绑定账号】\n" + ("\n".join(found) if found else "未查询到记录")
            await self.send_private_msg(websocket, qq_num, reply)
            return

        # [新增] 指令：查询名下CDK
        if any(re.search(x, msg_text, re.I) for x in ["查询名下CDK", "我的CDK", "我的cdk", "查询cdk", "查cdk", "查询名下卡密", "我的卡密", "查询卡密", "查卡密", "查询名下密钥", "我的密钥", "查询密钥", "查密钥"]):
            my_cdks = list(self.table_cdk.find(buyer=qq_num))
            if not my_cdks:
                await self.send_private_msg(websocket, qq_num, "❌ 查询失败：您名下暂无购买记录。")
                return

            lines = [f"【👤 您名下已购 CDK 列表】", "━━━━━━━━━━━━━━"]
            for s in my_cdks:
                status = "🔴 已售出" if s['is_used'] else "🟢 未售出"
                redeem_status = "✅ 游戏内已兑换" if s.get('is_redeemed') else "❌ 游戏内未兑换"
                lines.append(f"🔑 CDK: {s['cdk']}\n💰 价格: {s['price']}\n📅 购买时间: {s['buy_time'] or '未知'}\n📊 状态: {status} | {redeem_status}\n🏰 所属群号: {s['group_id']}")
                lines.append("--------------")
            
            full_msg = "\n".join(lines)
            await self.send_private_msg(websocket, qq_num, full_msg)
            return

        # 3. 绑定指令匹配
        bind_match = re.search(r"绑定\s*(\S+)\s*(?:账号[:：]?)?\s*(\S+)", msg_text, re.I)
        
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
                    # 仅统计当前区的绑定数量
                    if p[1] == str(qq_num) and p[0].rsplit(':', 1)[-1] == zone_name:
                        my_binds += 1
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
            "查下名下账号\n"
            "查询名下CDK"
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
                await self.send_group_msg(websocket, group_id, f"{user_id}为本群黑名单，已将他踢出群。", cmd_type="patrol")
                self.log_func(f"✅ 巡逻踢黑成功: 已自动清退成员 {user_id}")
            else:
                self.log_func(f"❌ 巡逻踢黑失败: 机器人在群 {group_id} 没有管理员权限。")

    async def handle_group_message(self, websocket, data):
        if not self.enable_group_manage and not self.enable_decoder and not self.enable_group_bind: return

        group_id = data.get("group_id")
        sender = data.get("sender", {})
        user_id = sender.get("user_id")
        
        # 优化昵称处理：处理缺失、过滤特殊字符
        raw_nickname = sender.get("nickname")
        if not raw_nickname:
            nickname = "无昵称"
        else:
            nickname = re.sub(r"[\r\n|:]", " ", str(raw_nickname)).strip()
            if not nickname: nickname = "无昵称"
            nickname = nickname[:20]
            
        role = sender.get("role", "member")
        raw_msg = data.get("raw_message", "").strip()
        self_id = data.get("self_id")
        message_id = data.get("message_id")

        # 1. 预处理消息：移除艾特、前后空格、并转小写用于匹配
        clean_msg = re.sub(rf"\[CQ:at,qq={self_id}(,name=[^\]]+)?\]", "", raw_msg).strip()
        # 再次移除可能残留的艾特文本形式（适配某些客户端渲染）
        clean_msg = re.sub(r"@\S+\s*", "", clean_msg).strip()

        cmd_type = ""
        target_qq = ""
        cmd_params = {}

        # 仅在开启群管理时处理管理指令
        if self.enable_group_manage:
            # --- 权限管理类 ---
            m_add_black = re.match(r"^/?(?:加入黑名单QQ|加黑|拉黑|封禁)\s*(?:qq)?\s*(.*)$", clean_msg, re.I)
            m_del_black = re.match(r"^/?(?:删除黑名单QQ|删黑|解黑|取消封禁)\s*(?:qq)?\s*(.*)$", clean_msg, re.I)
            
            if m_add_black:
                cmd_type = "add_black"
                val = m_add_black.group(1).strip()
                qq_match = re.search(r"(\d+)", val)
                if not qq_match:
                    await self.send_group_msg(websocket, group_id, "❌ 格式错误！\n正确格式：加黑 [QQ号]\n例如：加黑 123456", cmd_type="admin")
                    return
                target_qq = qq_match.group(1)
            elif m_del_black:
                cmd_type = "del_black"
                val = m_del_black.group(1).strip()
                qq_match = re.search(r"(\d+)", val)
                if not qq_match:
                    await self.send_group_msg(websocket, group_id, "❌ 格式错误！\n正确格式：删黑 [QQ号]\n例如：删黑 123456", cmd_type="admin")
                    return
                target_qq = qq_match.group(1)
            elif any(re.search(x, clean_msg, re.I) for x in ["黑名单QQ", "黑名单列表", "查看黑名单"]):
                cmd_type = "list_black"
            
            # --- 用户功能类 ---
            elif any(re.fullmatch(x, clean_msg, re.I) for x in ["功能", "菜单", "指令", "帮助", "help", "功能菜单", "/功能"]):
                cmd_type = "menu"
            elif any(re.search(x, clean_msg, re.I) for x in ["签到", "打卡", "每日签到", "我要签到"]):
                cmd_type = "checkin"
            elif any(re.search(x, clean_msg, re.I) for x in ["积分", "积分点", "我的积分", "查询积分", "查积分", "余额"]):
                cmd_type = "points"
            
            # --- CDK 管理类 ---
            elif re.match(r"^/?(?:新增CDK|添加CDK|新增卡密|添加卡密|新增密钥|添加密钥)\s*(.*)$", clean_msg, re.I):
                cmd_type = "add_cdk"
                m = re.match(r"^/?(?:新增CDK|添加CDK|新增卡密|添加卡密|新增密钥|添加密钥)\s*(.*)$", clean_msg, re.I)
                params_str = m.group(1).strip()
                parts = params_str.split()
                
                if len(parts) != 2:
                    await self.send_group_msg(websocket, group_id, "❌ 新增失败：参数不齐！\n正确格式：新增CDK [数量] [价格]\n例如：新增CDK 10 50", cmd_type="admin")
                    return

                try:
                    qty = int(parts[0])
                    price = int(parts[1])
                except ValueError:
                    await self.send_group_msg(websocket, group_id, "❌ 新增失败：数量和价格 must be 整数！", cmd_type="admin")
                    return

                if qty < 1 or qty > self.max_group_cdk:
                    await self.send_group_msg(websocket, group_id, f"❌ 新增失败：单次新增数量范围为 1-{self.max_group_cdk}！", cmd_type="admin")
                    return
                
                if price < 0:
                    await self.send_group_msg(websocket, group_id, "❌ 新增失败：价格不能为负数！", cmd_type="admin")
                    return

                cmd_params['qty'] = qty
                cmd_params['price'] = price
            elif any(re.search(x, clean_msg, re.I) for x in ["查询所有CDK", "列出所有CDK", "查询所有卡密", "列出所有卡密", "查询所有密钥", "列出所有密钥"]):
                cmd_type = "list_cdk"
            elif re.match(r"^(?:购买CDK|兑换CDK|买CDK|获取CDK|购买卡密|兑换卡密|买卡密|获取卡密|购买密钥|兑换密钥|买密钥|获取密钥)\s*(\d+)?.*$", clean_msg, re.I):
                cmd_type = "buy_cdk"
                m = re.match(r"^(?:购买CDK|兑换CDK|买CDK|获取CDK|购买卡密|兑换卡密|买卡密|获取卡密|购买密钥|兑换密钥|买密钥|获取密钥)\s*(\d+)?.*$", clean_msg, re.I)
                cmd_params['price_input'] = m.group(1)
            elif any(re.search(x, clean_msg, re.I) for x in ["删除所有CDK", "清空CDK", "删除所有卡密", "清空卡密", "删除所有密钥", "清空密钥"]):
                cmd_type = "clear_cdk"
            elif any(re.search(x, clean_msg, re.I) for x in ["清空所有积分", "清空本群积分", "重置所有积分", "清空积分"]):
                cmd_type = "clear_points"
            elif any(re.search(x, clean_msg, re.I) for x in ["查询名下CDK", "我的CDK", "我的cdk", "查询cdk", "查cdk", "查询名下卡密", "我的卡密", "查询卡密", "查卡密", "查询名下密钥", "我的密钥", "查询密钥", "查密钥"]):
                cmd_type = "list_my_cdk"
            elif re.match(r"^/?反查\s*(\S+)$", clean_msg, re.I):
                cmd_type = "reverse_lookup"
                m = re.match(r"^/?反查\s*(\S+)$", clean_msg, re.I)
                cmd_params['account'] = m.group(1).strip()

        # --- [独立匹配] 注册与查询类指令 (自然语言兼容) ---
        if self.enable_group_bind:
            # 1. 开区列表兼容
            if any(re.search(x, clean_msg, re.I) for x in ["开区列表", "有哪些区", "查看开区", "区服列表", "开什么区", "查询开区"]):
                cmd_type = "list_zones"
            # 2. 名下账号兼容
            elif any(re.search(x, clean_msg, re.I) for x in ["查下名下账号", "我的账号", "查账号", "名下账号", "我的绑定", "账号查询"]):
                cmd_type = "list_my_accounts"
            # 3. 绑定指令兼容 (保持 re.search 以捕获参数)
            elif re.search(r"(?:绑定|注册|账号绑定|我要绑定|帮我注册)\s*(\S+)\s*(?:账号[:：]?)?\s*(\S+)", clean_msg, re.I):
                # 这里仅标记类型，具体捕获在路由处再次执行以保持代码整洁
                cmd_type = "group_bind"

        # 判断是否为解码器相关消息 (增加群号过滤)
        is_decoder_msg = False
        if self.enable_decoder:
            # 如果设置了监听群号，则只在该群响应
            target_group = str(self.enable_decoder_group).strip()
            if not target_group or str(group_id) == target_group:
                # 兼容“解码版本”、“什么版本”、“版本是”
                if any(x in clean_msg for x in ["授权凭证", "支持版本", "有哪些版本"]):
                    is_decoder_msg = True
                elif re.search(r"(?:机器识别码|机器码)", clean_msg, re.I):
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
            return

        # --- [新增] 解码器功能处理 ---
        if is_decoder_msg:
            # 1. 指令触发说明
            if "授权凭证" in clean_msg:
                config = self.load_decoder_config()
                versions = config.get("versions", {})
                if not versions:
                    await self.send_group_msg(websocket, group_id, "⚠️ 解码器已开启，但未找到有效的版本配置(auth_config.json)。", cmd_type="decoder")
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
                    await self.send_group_msg(websocket, group_id, reply, cmd_type="decoder")
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
                        await self.send_group_msg(websocket, group_id, f"✅ [CQ:at,qq={user_id}] 授权码已通过【私聊】发送，请注意查收。", cmd_type="decoder")
                        self.log_func(f"✅ 解码成功: {user_id} | 版本: {matched_version}")
                    return
        # --- [解码器结束] ---

        # --- [新增] 群内绑定功能处理 ---
        if self.enable_group_bind:
            # 如果设置了绑定群号，则只在该群响应
            target_bind_group = str(self.enable_bind_group).strip()
            if not target_bind_group or str(group_id) == target_bind_group:
                # 兼容“绑定”、“注册”、“账号绑定”
                bind_match = re.search(r"(?:绑定|注册|账号绑定)\s*(\S+)\s*(?:账号[:：]?)?\s*(\S+)", clean_msg, re.I)
                if bind_match:
                    zone_name = re.sub(r"[,，:：\-\s]", "", bind_match.group(1).strip())
                    account = re.sub(r"[,，:：\-\s]", "", bind_match.group(2).strip())
                    
                    filepath = self.get_filepath()
                    zones, records = read_file_data(filepath)
                    zones_list_txt = self.get_zones_msg(zones, records)

                    # 1. 校验区服
                    if zone_name not in zones:
                        fail_msg = f"[CQ:at,qq={user_id}] ❌ 注册失败：【{zone_name}】不在开区名单内！\n\n{zones_list_txt}"
                        await self.send_group_msg(websocket, group_id, fail_msg, cmd_type="group_bind")
                        return

                    # 2. 校验账号占用和个人上限
                    my_binds = 0
                    account_registered = False
                    for r in records:
                        try:
                            p = r.split('|')
                            if p[0] == f"{account}:{zone_name}": account_registered = True
                            # 仅统计当前区的绑定数量
                            if p[1] == str(user_id) and p[0].rsplit(':', 1)[-1] == zone_name:
                                my_binds += 1
                        except: continue

                    if account_registered:
                        fail_msg = f"[CQ:at,qq={user_id}] ❌ 注册失败：账号【{account}】在【{zone_name}】已被占用！\n\n{zones_list_txt}"
                        await self.send_group_msg(websocket, group_id, fail_msg, cmd_type="group_bind")
                        return

                    if my_binds >= self.max_binds:
                        fail_msg = f"[CQ:at,qq={user_id}] ❌ 注册失败：您在此区的名额已满({self.max_binds}个)！\n\n{zones_list_txt}"
                        await self.send_group_msg(websocket, group_id, fail_msg, cmd_type="group_bind")
                        return

                    # 3. 写入记录
                    new_record = f"{account}:{zone_name}|{user_id}|{nickname}"
                    records.append(new_record)
                    if write_file_data(filepath, zones, records):
                        success_msg = f"[CQ:at,qq={user_id}] 🎉 绑定成功！\n区服：{zone_name}\n账号：{account}\n祝您游戏愉快！"
                        await self.send_group_msg(websocket, group_id, success_msg, cmd_type="group_bind")
                        self.log_func(f"✅ 群内绑定成功: {new_record}")
                    else:
                        fail_msg = f"[CQ:at,qq={user_id}] ❌ 绑定失败：系统无法写入记录，请联系管理（可能由昵称特殊字符引起）。"
                        await self.send_group_msg(websocket, group_id, fail_msg, cmd_type="group_bind")
                        self.log_func(f"❌ 群内绑定失败: {new_record}")
                    return
        # --- [群内绑定结束] ---

        if not cmd_type: return

        # 2. 权限验证
        is_owner = role == "owner"
        is_admin = role in ["owner", "admin"]

        if cmd_type in ["add_cdk", "clear_cdk"]:
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
            # 动态读取本群未使用的CDK价格
            cdks_in_db = list(self.table_cdk.find(group_id=group_id, is_used=0))
            price_stats = {}
            for s in cdks_in_db:
                p = s['price']
                price_stats[p] = price_stats.get(p, 0) + 1
            
            cdk_info = ""
            if not price_stats:
                cdk_info = " (暂无可用CDK)"
            else:
                prices_str = "/".join([f"{p}积分" for p in sorted(price_stats.keys())])
                cdk_info = f" ({prices_str})"

            # 判断当前群是否为指定的绑定群
            is_target_bind_group = False
            if self.enable_group_bind:
                target_bind_group = str(self.enable_bind_group).strip()
                if not target_bind_group or str(group_id) == target_bind_group:
                    is_target_bind_group = True

            if is_target_bind_group:
                reply = (
                    "【🛠️ 机器人功能菜单】\n"
                    "签到 (获得1积分)\n"
                    "积分 (查看个人积分)\n"
                    "绑定 区号 游戏账号 (例如:绑定 热血传奇二区 qwe123asd)\n"
                    "开区列表\n"
                    "查下名下账号\n"
                    f"购买CDK{cdk_info}\n"
                    "查询名下CDK (查看已购卡密)\n"
                    "--- 管理员指令 ---\n"
                    "查询所有CDK (仅限群主)\n"
                    "新增CDK 数量 价格 (仅限群主)\n"
                    "删除所有CDK (仅限群主)\n"
                    "清空所有积分 (仅限群主)\n"
                    "黑名单QQ (查看列表)\n"
                    "加黑 QQ (拉黑)\n"
                    "删黑 QQ (移出)"
                )
            else:
                reply = (
                    "【🛠️ 机器人功能菜单】\n"
                    "签到 (获得1积分)\n"
                    "积分 (查看个人积分)\n"
                    f"购买CDK{cdk_info}\n"
                    "查询名下CDK (查看已购卡密)\n"
                    "--- 管理员指令 ---\n"
                    "查询所有CDK (仅限群主)\n"
                    "新增CDK 数量 价格 (仅限群主)\n"
                    "删除所有CDK (仅限群主)\n"
                    "清空所有积分 (仅限群主)\n"
                    "黑名单QQ (查看列表)\n"
                    "加黑 QQ (拉黑)\n"
                    "删黑 QQ (移出)"
                )
            await self.send_group_msg(websocket, group_id, reply, cmd_type="menu")

        elif cmd_type == "list_zones":
            if not self.enable_group_bind: return
            target_bind_group = str(self.enable_bind_group).strip()
            if target_bind_group and str(group_id) != target_bind_group: return
            
            filepath = self.get_filepath()
            zones, records = read_file_data(filepath)
            reply = f"[CQ:at,qq={user_id}] \n" + self.get_zones_msg(zones, records)
            await self.send_group_msg(websocket, group_id, reply, cmd_type="list_zones")

        elif cmd_type == "list_my_accounts":
            if not self.enable_group_bind: return
            target_bind_group = str(self.enable_bind_group).strip()
            if target_bind_group and str(group_id) != target_bind_group: return

            filepath = self.get_filepath()
            _, records = read_file_data(filepath)
            found = []
            for r in records:
                try:
                    parts = r.split('|')
                    if len(parts) >= 2 and parts[1] == str(user_id):
                        acc_zone = parts[0]
                        # 使用 rsplit 适配账号含冒号的情况
                        acc, zone = acc_zone.rsplit(':', 1)
                        found.append(f"账号：{acc} ({zone})")
                except: pass
            
            content = "\n".join(found) if found else "未查询到记录"
            reply = f"[CQ:at,qq={user_id}] \n【👤 您名下已绑定账号】\n{content}"
            await self.send_group_msg(websocket, group_id, reply, cmd_type="list_my_accounts")

        elif cmd_type == "list_my_cdk":
            my_cdks = list(self.table_cdk.find(group_id=group_id, buyer=user_id))
            if not my_cdks:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] ❌ 查询失败：您名下暂无购买记录。")
                return

            lines = [f"【👤 您名下已购 CDK 列表】", "━━━━━━━━━━━━━━"]
            for s in my_cdks:
                redeem_status = "✅ 游戏内已兑换" if s.get('is_redeemed') else "❌ 游戏内未兑换"
                lines.append(f"🔑 CDK: {s['cdk']}\n💰 价格: {s['price']}\n📅 购买时间: {s['buy_time'] or '未知'}\n📊 兑换状态: {redeem_status}")
                lines.append("--------------")
            
            full_msg = "\n".join(lines)
            await self.send_private_msg(websocket, user_id, full_msg)
            await self.send_group_msg(websocket, group_id, f"✅ [CQ:at,qq={user_id}] 已将您名下的 {len(my_cdks)} 条 CDK 记录及游戏兑换状态私聊发送给您。", cmd_type="list_my_cdk")

        elif cmd_type == "add_cdk":
            import random
            import string
            
            qty = cmd_params['qty']
            price = cmd_params['price']
            
            # 检查当前数据库总量
            current_total = self.table_cdk.count(group_id=group_id)
            if current_total + qty > self.max_group_cdk:
                available = self.max_group_cdk - current_total
                await self.send_group_msg(websocket, group_id, 
                    f"❌ 新增失败：本群 CDK 总容量上限为 {self.max_group_cdk} 条。\n"
                    f"当前已存在：{current_total} 条\n"
                    f"本次尝试新增：{qty} 条\n"
                    f"剩余空间：{max(0, available)} 条\n"
                    f"💡 请先执行【删除所有CDK】后再批量新增。")
                return

            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            success_count = 0
            for _ in range(qty):
                random_cdk = ''.join(random.choices(string.digits, k=13))
                try:
                    self.table_cdk.insert(dict(
                        group_id=group_id,
                        cdk=random_cdk,
                        is_used=0,
                        is_redeemed=0, # 新增：是否在游戏内已兑换 (0:未兑换, 1:已兑换)
                        price=price,
                        buyer=None,
                        create_time=now_str,
                        buy_time=None
                    ))
                    success_count += 1
                except Exception as e:
                    self.log_func(f"❌ 数据库写入失败: {e}")

            await self.send_group_msg(websocket, group_id, 
                f"✅ CDK 生成成功！\n群号：{group_id}\n新增数量：{success_count}\n单价：{price} 积分\n时间：{now_str}", cmd_type="admin")

        elif any(clean_msg == x for x in ["查询所有CDK", "查询所有卡密", "查询所有密钥"]):
            if not is_owner:
                await self.send_group_msg(websocket, group_id, f"🚫 [CQ:at,qq={user_id}] 权限不足！该指令仅限【群主】使用。")
                return
            
            all_cdks = list(self.table_cdk.find(group_id=group_id))
            if not all_cdks:
                await self.send_group_msg(websocket, group_id, "❌ 查询失败：本群数据库中暂无 CDK 记录。")
                return

            # --- 1. 生成详情版消息 ---
            lines_detail = [f"【📋 群 {group_id} CDK 详情全量列表】", "━━━━━━━━━━━━━━"]
            for s in all_cdks:
                status = "🔴 已售出" if s['is_used'] else "🟢 未售出"
                redeem_status = "✅ 已兑换" if s.get('is_redeemed') else "❌ 未兑换"
                buyer_info = f" | 购买人: {s['buyer']}" if s['buyer'] else ""
                lines_detail.append(f"🔑 CDK: {s['cdk']}\n💰 价格: {s['price']} | 状态: {status} | 游戏: {redeem_status}{buyer_info}")
                lines_detail.append("--------------")
            
            detail_msg = "\n".join(lines_detail)
            await self.send_private_msg(websocket, user_id, detail_msg)

            # --- 2. 生成简洁版消息 ---
            data_map = {} # { price: { "used": [], "unused": [], "redeemed_count": 0 } }
            for s in all_cdks:
                p = s['price']
                if p not in data_map:
                    data_map[p] = {"used": [], "unused": [], "redeemed_count": 0}
                if s['is_used']:
                    data_map[p]["used"].append(s['cdk'])
                else:
                    data_map[p]["unused"].append(s['cdk'])
                if s.get('is_redeemed'):
                    data_map[p]["redeemed_count"] += 1

            lines_brief = [f"【📋 群 {group_id} CDK 简洁分类报表】", "━━━━━━━━━━━━━━"]
            for price in sorted(data_map.keys()):
                lines_brief.append(f"💰 价格为 {price} 积分")
                used_list = data_map[price]["used"]
                redeemed_count = data_map[price]["redeemed_count"]
                lines_brief.append(f"  🔴 已购买：{len(used_list)} 条 (其中游戏已兑换：{redeemed_count})")
                
                unused_list = data_map[price]["unused"]
                lines_brief.append(f"  🟢 未购买：{len(unused_list)} 条")
                lines_brief.append("--------------")
            
            brief_msg = "\n".join(lines_brief)
            await self.send_private_msg(websocket, user_id, brief_msg)
            
            await self.send_group_msg(websocket, group_id, f"✅ 已将本群 CDK 的【详情列表】与【简洁报表】私聊发送给群主。", cmd_type="admin")

        elif re.match(r"^购买(?:CDK|卡密|密钥)(?:\s+(\d+))?$", clean_msg):
            # 获取本群所有未使用的CDK价格
            available_cdks = list(self.table_cdk.find(group_id=group_id, is_used=0))
            if not available_cdks:
                await self.send_group_msg(websocket, group_id, "❌ 购买失败：当前仓库内暂无可用 CDK。", cmd_type="buy_cdk")
                return

            distinct_prices = sorted(list(set([s['price'] for s in available_cdks])))
            
            m = re.match(r"^购买(?:CDK|卡密|密钥)(?:\s+(\d+))?$", clean_msg)
            input_price_str = m.group(1)
            
            target_price = None
            if input_price_str:
                target_price = int(input_price_str)
            else:
                if len(distinct_prices) == 1:
                    target_price = distinct_prices[0]
                else:
                    prices_list = "/".join([str(p) for p in distinct_prices])
                    await self.send_group_msg(websocket, group_id, f"💡 请输入具体的购买价格，例如：购买CDK {distinct_prices[0]}\n当前可用价格：{prices_list}")
                    return

            # 校验该价格是否有库存
            cdk_record = self.table_cdk.find_one(group_id=group_id, price=target_price, is_used=0)
            if not cdk_record:
                await self.send_group_msg(websocket, group_id, f"❌ 购买失败：价格为 {target_price} 的 CDK 已售罄。", cmd_type="buy_cdk")
                return
            
            # 校验名下购买上限
            my_cdks_count = self.table_cdk.count(group_id=group_id, buyer=user_id)
            if my_cdks_count >= self.max_cdk_binds:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] ❌ 购买失败：您在本群的 CDK 购买名额已满({self.max_cdk_binds}个)！", cmd_type="buy_cdk")
                return

            # 校验积分
            user_record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not user_record or user_record['points'] < target_price:
                current_pts = user_record['points'] if user_record else 0
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] ❌ 积分不足！购买需 {target_price} 积分，你当前仅有 {current_pts} 积分。", cmd_type="buy_cdk")
                return
            
            # 执行购买
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_points = user_record['points'] - target_price
            
            self.table_group.update(dict(id=user_record['id'], points=new_points), ['id'])
            self.table_cdk.update(dict(
                id=cdk_record['id'], 
                is_used=1, 
                buyer=user_id, 
                buy_time=now_str
            ), ['id'])
            
            # --- [新增] 自动同步到游戏文本 ---
            try:
                # 确保目录存在
                os.makedirs(os.path.dirname(self.game_unused_file), exist_ok=True)
                with open(self.game_unused_file, "a", encoding="gbk") as f:
                    f.write(f"{cdk_record['cdk']}\n")
                self.log_func(f"📤 游戏同步：CDK {cdk_record['cdk']} 已写入【未使用CDK.txt】")
            except Exception as e:
                self.log_func(f"❌ 游戏同步失败: {e}")
            
            # 私聊发送CDK给购买者
            private_msg = (
                f"🎉 购买成功！\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔑 您的 CDK：{cdk_record['cdk']}\n"
                f"💰 消耗积分：{target_price}\n"
                f"📅 购买时间：{now_str}\n"
                f"━━━━━━━━━━━━━━"
            )
            await self.send_private_msg(websocket, user_id, private_msg)
            
            # 群内提示
            await self.send_group_msg(websocket, group_id, f"🎉 [CQ:at,qq={user_id}] 购买成功！\n消耗积分：{target_price}\nCDK已通过【私聊】发送，请注意查收。", cmd_type="buy_cdk")

        elif cmd_type == "clear_cdk":
            try:
                self.table_cdk.delete(group_id=group_id)
                
                # --- [新增] 同步清空游戏文本 ---
                if os.path.exists(self.game_unused_file):
                    try:
                        with open(self.game_unused_file, "w", encoding="gbk") as f:
                            f.write("")
                        self.log_func(f"📤 游戏同步：已同步清空【未使用CDK.txt】")
                    except Exception as fe:
                        self.log_func(f"⚠️ 游戏文本清空失败: {fe}")

                await self.send_group_msg(websocket, group_id, "🧹 已成功清空本群所有 CDK 记录及游戏内未使用文本。", cmd_type="admin")
                self.log_func(f"✅ CDK清空: 群 {group_id}")
            except Exception as e:
                await self.send_group_msg(websocket, group_id, f"❌ 清空失败：数据库操作异常。\n错误信息：{str(e)}")
                self.log_func(f"❌ CDK清空失败: {e}")

        elif cmd_type == "checkin":
            if not self.enable_checkin: return
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not record:
                self.table_group.insert(dict(group_id=group_id, user_nickname=nickname, user_id=user_id, points=1, last_checkin_date=today))
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到成功，积分+1", cmd_type="checkin")
            elif record['last_checkin_date'] == today:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到失败，今天已经签到过了~", cmd_type="checkin")
            else:
                self.table_group.update(dict(id=record['id'], points=record['points'] + 1, last_checkin_date=today, user_nickname=nickname), ['id'])
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 签到成功，积分+1", cmd_type="checkin")
                
        elif cmd_type == "points":
            if not self.enable_checkin: return
            record = self.table_group.find_one(group_id=group_id, user_id=user_id)
            if not record:
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 没有你的记录", cmd_type="points")
            else:
                pts = record['points']
                await self.send_group_msg(websocket, group_id, f"[CQ:at,qq={user_id}] 你拥有积分是:{pts}，签到时间为：{record['last_checkin_date']}", cmd_type="points")

        elif cmd_type == "list_black":
            bl_records = list(self.table_blacklist.find(group_id=group_id))
            if not bl_records:
                await self.send_group_msg(websocket, group_id, "当前群的黑名单为空。", cmd_type="admin")
            else:
                bl_qqs = [str(x['user_id']) for x in bl_records]
                await self.send_group_msg(websocket, group_id, f"当前群黑名单包含QQ: {', '.join(bl_qqs)}", cmd_type="admin")

        elif cmd_type == "add_black" and target_qq:
            if not self.table_blacklist.find_one(group_id=group_id, user_id=target_qq):
                self.table_blacklist.insert(dict(group_id=group_id, user_id=target_qq))
                await self.send_group_msg(websocket, group_id, f"已将QQ {target_qq} 成功加入黑名单。", cmd_type="admin")
                self.log_func(f"✅ 加入黑名单: {target_qq}")
                
                if self.enable_patrol:
                    await self.call_api(websocket, "set_group_kick", {"group_id": group_id, "user_id": int(target_qq), "reject_add_request": False})
            else:
                await self.send_group_msg(websocket, group_id, f"QQ {target_qq} 已经在黑名单列表中了。", cmd_type="admin")

        elif cmd_type == "del_black" and target_qq:
            self.table_blacklist.delete(group_id=group_id, user_id=target_qq)
            await self.send_group_msg(websocket, group_id, f"已将QQ {target_qq} 移出黑名单。", cmd_type="admin")
            self.log_func(f"✅ 移出黑名单: {target_qq}")

        elif cmd_type == "clear_points":
            if not is_owner:
                await self.send_group_msg(websocket, group_id, f"🚫 [CQ:at,qq={user_id}] 权限不足！该指令仅限【群主】使用。")
                return
            try:
                # 更新本群所有玩家动积分为 0
                self.table_group.update(dict(group_id=group_id, points=0), ['group_id'])
                await self.send_group_msg(websocket, group_id, "🧹 已成功清空本群所有玩家的积分。", cmd_type="admin")
                self.log_func(f"✅ 积分清空: 群 {group_id}")
            except Exception as e:
                await self.send_group_msg(websocket, group_id, f"❌ 清空失败：数据库操作异常。\n错误信息：{str(e)}")
                self.log_func(f"❌ 积分清空失败: {e}")

        elif cmd_type == "reverse_lookup":
            if not is_owner:
                await self.send_group_msg(websocket, group_id, f"🚫 [CQ:at,qq={user_id}] 权限不足！该指令仅限【群主】使用。")
                return
            
            account_to_find = cmd_params['account']
            filepath = self.get_filepath()
            zones, records = read_file_data(filepath)
            
            found_qqs = []
            for r in records:
                try:
                    parts = r.split('|')
                    if len(parts) >= 2:
                        acc_zone = parts[0]
                        # 格式是 账号:区服
                        acc = acc_zone.rsplit(':', 1)[0]
                        if acc.lower() == account_to_find.lower():
                            found_qqs.append(parts[1])
                except:
                    continue
            
            if not found_qqs:
                await self.send_group_msg(websocket, group_id, f"❌ 反查失败：未找到游戏账号为【{account_to_find}】的注册记录。", cmd_type="admin")
                return
            
            unique_qqs = list(set(found_qqs))
            at_msg = " ".join([f"[CQ:at,qq={qq}]" for qq in unique_qqs])
            reply = f"🔍 账号【{account_to_find}】的反查结果：\n共找到 {len(unique_qqs)} 个绑定的QQ号：\n{at_msg}"
            await self.send_group_msg(websocket, group_id, reply, cmd_type="admin")



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

    async def handle_friend_request(self, websocket, data):
        """处理好友请求"""
        if not self.enable_auto_friend: return

        user_id = data.get("user_id")
        flag = data.get("flag")
        self.log_func(f"🔔 发现好友请求：{user_id}，正在自动通过...")
        await self.call_api(websocket, "set_friend_add_request", {
            "flag": flag,
            "approve": True
        })

    async def manual_sync_text_to_db(self):
        """手动强制同步：从日志文件更新到数据库"""
        self.log_func("📥 正在执行强制同步：日志 -> 数据库...")
        try:
            if not os.path.exists(self.game_used_log_file):
                self.log_func("❌ 同步失败：找不到已使用日志文件")
                return
            
            # 复用同步逻辑
            content = ""
            try:
                with open(self.game_used_log_file, "r", encoding="gbk") as f:
                    content = f.read().strip()
            except UnicodeDecodeError:
                with open(self.game_used_log_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()

            if not content:
                self.log_func("💡 日志文件为空，无需同步")
                return

            lines = content.splitlines()
            processed_count = 0
            for line in lines:
                match = re.search(r"使用码【(\d+)】", line)
                if match:
                    cdk_code = match.group(1)
                    record = self.table_cdk.find_one(cdk=cdk_code)
                    if record and not record.get("is_redeemed"):
                        self.table_cdk.update(dict(id=record['id'], is_redeemed=1), ['id'])
                        processed_count += 1
            
            if processed_count > 0:
                with open(self.game_used_log_file, "w", encoding="gbk") as f:
                    f.write("")
                self.log_func(f"✅ 强制同步完成：共更新 {processed_count} 条记录")
            else:
                self.log_func("💡 未发现可更新的有效记录")
        except Exception as e:
            self.log_func(f"❌ 强制同步异常: {e}")

    async def manual_sync_db_to_text(self):
        """手动强制同步：将数据库中已购买但未兑换的 CDK 重新写入文件"""
        self.log_func("📤 正在执行强制同步：数据库 -> 未使用文件...")
        try:
            # 查找所有 已购买(is_used=1) 且 未兑换(is_redeemed=0) 的记录
            pending_cdks = list(self.table_cdk.find(is_used=1, is_redeemed=0))
            
            # 确保目录存在
            os.makedirs(os.path.dirname(self.game_unused_file), exist_ok=True)
            
            # 覆盖写入文件 (即使列表为空也写入，以达到清空文件的效果)
            with open(self.game_unused_file, "w", encoding="gbk") as f:
                for item in pending_cdks:
                    f.write(f"{item['cdk']}\n")
            
            if not pending_cdks:
                self.log_func("✅ 强制同步完成：数据库中无待兑换记录，已清空文本文件")
            else:
                self.log_func(f"✅ 强制同步完成：已将 {len(pending_cdks)} 条待兑换 CDK 写入文件")
        except Exception as e:
            self.log_func(f"❌ 强制同步异常: {e}")

    async def sync_game_records(self):
        """后台任务：循环读取游戏的 已使用.txt 并同步到数据库"""
        self.log_func("🔄 游戏数据同步任务已启动")
        while self.running:
            try:
                if os.path.exists(self.game_used_log_file):
                    # 以 GBK 读取 (通常游戏引擎使用 GBK)
                    content = ""
                    try:
                        with open(self.game_used_log_file, "r", encoding="gbk") as f:
                            content = f.read().strip()
                    except UnicodeDecodeError:
                        with open(self.game_used_log_file, "r", encoding="utf-8") as f:
                            content = f.read().strip()

                    if content:
                        lines = content.splitlines()
                        processed_count = 0
                        for line in lines:
                            # 匹配格式：...:使用码【1124717133318】
                            match = re.search(r"使用码【(\d+)】", line)
                            if match:
                                cdk_code = match.group(1)
                                # 在数据库中标记为已兑换
                                record = self.table_cdk.find_one(cdk=cdk_code)
                                if record and not record.get("is_redeemed"):
                                    self.table_cdk.update(dict(id=record['id'], is_redeemed=1), ['id'])
                                    self.log_func(f"📥 游戏同步：检测到兑换成功 | CDK: {cdk_code}")
                                    processed_count += 1
                        
                        if processed_count > 0:
                            # 清空文件，防止重复读取
                            with open(self.game_used_log_file, "w", encoding="gbk") as f:
                                f.write("")
                
            except Exception as e:
                self.log_func(f"⚠️ 同步任务异常: {e}")
            
            await asyncio.sleep(1) # 每 1 秒同步一次

    async def start(self):
        self.running = True
        try:
            self.db = dataset.connect(DB_URL)
            self.table_group = self.db['QQgroup']
            self.table_blacklist = self.db['Blacklist']
            self.table_bot_admin = self.db['BotGroupAdmin']
            self.table_cdk = self.db['CDK']
            self.log_func("✅ 数据库加载成功")
        except Exception as e:
            self.log_func(f"❌ 数据库异常: {e}")
            return

        # 启动后台同步任务
        asyncio.create_task(self.sync_game_records())

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
                            req_type = data.get("request_type")
                            if req_type == "group":
                                asyncio.create_task(self.handle_group_request(websocket, data))
                            elif req_type == "friend":
                                asyncio.create_task(self.handle_friend_request(websocket, data))
                    except json.JSONDecodeError: pass
        except Exception as e:
            self.log_func(f"❌ 连接异常或断开: {e}")
        self.running = False
