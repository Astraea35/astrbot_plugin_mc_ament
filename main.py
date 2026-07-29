import os, io, aiohttp, re, logging
from PIL import Image as PILImage, ImageDraw, ImageFont
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Star, Context
# 完美同步表情转存插件的组件：引入 Reply, Image, At, Plain
from astrbot.api.message_components import Image, At, Plain, Reply

logger = logging.getLogger("astrbot")

class MCAdvancementPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config = self.context.get_config()
        self.plugin_dir = os.path.dirname(__file__)
        self.assets_dir = os.path.join(self.plugin_dir, "assets")
        self.bg_path = os.path.join(self.assets_dir, "AdvancementMade_BG.png")
        self.font_path = os.path.join(self.assets_dir, "MinecraftAE.ttf")
        self.local_default_icon = os.path.join(self.assets_dir, "fallback_icon.jpg")

    @filter.command("mc成就")
    async def mc_task(self, event: AstrMessageEvent):
        '''生成普通成就。用法: /mc成就 [标题] [描述]'''
        yield await self._process_request(event, "task")

    @filter.command("mc挑战")
    async def mc_challenge(self, event: AstrMessageEvent):
        '''生成挑战成就。用法: /mc挑战 [标题] [描述]'''
        yield await self._process_request(event, "challenge")

    async def _process_request(self, event: AstrMessageEvent, m_type):
        # 1. 提取纯文本参数
        clean_text = ""
        for comp in event.message_obj.message:
            if isinstance(comp, Plain):
                clean_text += comp.text + " "
                
        content = re.sub(r'^/\S+\s*', '', clean_text.strip()).strip()
        args = content.split() if content else []
        
        title, desc = "获得成就！", "开启了新的一天"
        if len(args) >= 2: title, desc = args[0], args[1]
        elif len(args) == 1: title = args[0]

        try:
            # 2. 图像资源预处理
            if not os.path.exists(self.bg_path):
                return event.plain_result("错误: 缺少背景图资源")
            
            base_bg = PILImage.open(self.bg_path).convert("RGBA")
            if base_bg.height < 100:
                base_bg = base_bg.resize((int(base_bg.width * (128/base_bg.height)), 128), PILImage.NEAREST)
            bw, bh = base_bg.size

            # 3. 字体加载
            try:
                f_title = ImageFont.truetype(self.font_path, 32)
                f_desc = ImageFont.truetype(self.font_path, 24)
            except:
                logger.warning("[MC成就] 找不到字体，将使用系统默认字体")
                f_title = f_desc = ImageFont.load_default()

            # --- 4. 原生且最稳健的图标提取逻辑 (向表情转存插件看齐) ---
            icon_url = None
            
            for comp in event.message_obj.message:
                # 情况A: 直接抓取当前消息链里的图片 (兼容直发图和适配器自带解析的图)
                if isinstance(comp, Image):
                    icon_url = getattr(comp, "url", getattr(comp, "file", None))
                    if icon_url: break
                
                # 情况B: 抓取当前消息里的 @某人
                elif isinstance(comp, At):
                    icon_url = f"https://q.qlogo.cn/g?b=qq&nk={comp.qq}&s=640"
                    break
                    
                # 情况C: 抓取底层的引用回复 Reply 组件
                elif isinstance(comp, Reply):
                    # 有些平台在遇到 Reply 时，会把原图的链接包裹在 Reply 的底层字符串中
                    # 我们用强正则兜底，只要看到像图片链接的，直接抽出来
                    urls = re.findall(r'(https?://[^\s\'"<>\[\]]+)', str(comp))
                    for u in urls:
                        if 'qpic' in u or 'image' in u.lower():
                            icon_url = u
                            break
                    if not icon_url and urls:
                        icon_url = urls[0]
                    if icon_url: break

            # 5. 渲染布局计算
            tmp_draw = ImageDraw.Draw(PILImage.new("RGBA", (1, 1)))
            t_w = tmp_draw.textbbox((0, 0), title, font=f_title)[2]
            d_w = tmp_draw.textbbox((0, 0), desc, font=f_desc)[2]
            
            actual_text_w = max(t_w, d_w)
            target_width = int(actual_text_w * 1.2) + 180
            if target_width < 450: target_width = 450

            edge = 64
            left_p = base_bg.crop((0, 0, edge, bh))
            mid_p = base_bg.crop((edge, 0, bw - edge, bh))
            right_p = base_bg.crop((bw - edge, 0, bw, bh))
            
            final_bg = PILImage.new("RGBA", (target_width, bh), (0, 0, 0, 0))
            final_bg.paste(left_p, (0, 0))
            final_bg.paste(right_p, (target_width - edge, 0))
            if target_width > edge * 2:
                final_bg.paste(mid_p.resize((target_width - edge * 2, bh), PILImage.NEAREST), (edge, 0))

            title_color, shadow_color = (255, 255, 85), (63, 63, 21)
            if m_type == "challenge":
                final_bg = PILImage.alpha_composite(final_bg, PILImage.new("RGBA", final_bg.size, (251, 0, 251, 35)))
                title_color, shadow_color = (251, 0, 251), (62, 0, 62)

            # 合成图标
            icon = await self._load_icon(icon_url)
            icon = icon.resize((64, 64), PILImage.NEAREST)
            final_bg.paste(icon, (32, 32), icon if icon.mode == 'RGBA' else None)

            # 绘制文字
            draw = ImageDraw.Draw(final_bg)
            tx, ty1, ty2 = 115, 28, 70 
            draw.text((tx+2, ty1+2), title, font=f_title, fill=shadow_color)
            draw.text((tx, ty1), title, font=f_title, fill=title_color)
            draw.text((tx+2, ty2+2), desc, font=f_desc, fill=(60, 60, 60))
            draw.text((tx, ty2), desc, font=f_desc, fill=(255, 255, 255))

            # --- 6. 导出格式与压缩处理 (完全由 WebUI 控制) ---
            out_fmt = self.config.get("output_format", "PNG").upper()
            if out_fmt == "JPG": out_fmt = "JPEG"
            out_quality = int(self.config.get("output_quality", 90))

            export_img = final_bg
            # JPEG 不支持透明图层，垫一层深灰色底图模拟游戏UI背景
            if out_fmt == "JPEG" and final_bg.mode == "RGBA":
                export_img = PILImage.new("RGB", final_bg.size, (33, 33, 33))
                export_img.paste(final_bg, mask=final_bg.split()[3])

            save_kwargs = {"format": out_fmt}
            if out_fmt in ["JPEG", "WEBP"]: 
                save_kwargs["quality"] = out_quality

            out = io.BytesIO()
            export_img.save(out, **save_kwargs)
            
            return event.chain_result([Image.fromBytes(out.getvalue())])

        except Exception as e:
            logger.error(f"[MC成就] 渲染异常: {e}", exc_info=True)
            return event.plain_result(f"生成失败: {str(e)}")

    async def _load_icon(self, url):
        if url:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                    async with s.get(url, headers=headers) as r:
                        if r.status == 200: 
                            return PILImage.open(io.BytesIO(await r.read())).convert("RGBA")
            except Exception as e:
                logger.warning(f"[MC成就] 下载图标失败, URL: {url}, 原因: {e}")
        
        if os.path.exists(self.local_default_icon): 
            return PILImage.open(self.local_default_icon).convert("RGBA")
        return PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))