import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image as PILImage
from astrbot.api.message_components import Image, Reply


spec = importlib.util.spec_from_file_location(
    "mc_telegram_test", Path(__file__).resolve().parents[1] / "main.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.asyncio
@pytest.mark.parametrize("quoted", [False, True])
async def test_local_attachment_is_used_for_icon(tmp_path, quoted):
    path = tmp_path / "icon.png"
    PILImage.new("RGB", (20, 20), "red").save(path)
    image = Image.fromFileSystem(str(path))
    components = [Reply(id="1", chain=[image])] if quoted else [image]
    event = SimpleNamespace(message_obj=SimpleNamespace(message=components))
    plugin = module.MCAdvancementPlugin.__new__(module.MCAdvancementPlugin)
    plugin.local_default_icon = str(tmp_path / "missing.png")
    icon_path = await plugin._find_icon(event)
    assert Path(icon_path) == path
    icon = await plugin._load_icon(icon_path)
    assert icon.size == (20, 20)
    assert icon.getpixel((0, 0)) == (255, 0, 0, 255)
