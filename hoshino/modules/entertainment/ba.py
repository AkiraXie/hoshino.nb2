
from math import radians, tan
from PIL import Image, ImageDraw, ImageFont
from hoshino import Service, R, T_State
from hoshino.util import img_to_segment
from hoshino.rule import ArgumentParser
sv = Service("balogo", enable_on_default=False)
try:
    FONTSIZE = 84
    FONT = ImageFont.truetype(R.img("ba","Merged.otf").path, FONTSIZE)
    HALO = R.img("ba", "halo.png").open().resize((250, 250), Image.Resampling.BICUBIC)
    CROSS = R.img("ba", "cross.png").open()
except:
    sv.logger.error("cannot load ba resources")
parser = ArgumentParser()
parser.add_argument("ltext")
parser.add_argument("rtext")
cmd = sv.on_shell_command("ba", parser=parser, only_group=False)

def draw(ltext: str, rtext: str, dx: int = 76, dy: int = -7) -> Image.Image:
    width = FONTSIZE * (len(ltext) + len(rtext) + 2)
    height = FONTSIZE * 2 + 50
    blue = (18, 138, 250, 255)
    gray = (43, 43, 43, 255)
    white = (255, 255, 255, 255)
    angle = 20
    dist = height * tan(radians(angle))
    data = (1, tan(radians(angle)), -dist, 0, 1, 0)
    mid = (304, 144)
    offset = 12
    polygon_xy = [
        (138, 428),
        (mid[0] - offset, mid[1] - offset),
        (mid[0] + offset, mid[1] + offset),
    ]
    polygon_xy_second = [
        (484, 222),
        (mid[0] - offset, mid[1] + offset),
        (mid[0] + offset, mid[1] - offset),
    ]
    image = Image.new("RGBA", (500, 500), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(polygon_xy, fill=white)
    draw.polygon(polygon_xy_second, fill=white)
    draw.bitmap((0, 0), CROSS, fill=blue)
    image = image.resize((250, 250), Image.Resampling.BICUBIC)
    left = Image.new(
        "RGBA", (FONTSIZE * (len(ltext) + 2), FONTSIZE * 2), (255, 255, 255, 0)
    )
    draw = ImageDraw.Draw(left)
    draw.text((0, 0), ltext, font=FONT, fill=blue)
    left = left.transform(
        left.size, Image.Transform.AFFINE, data, Image.Resampling.BICUBIC
    )
    left = left.crop(left.getbbox())
    right = Image.new(
        "RGBA", (FONTSIZE * (len(rtext) + 2), FONTSIZE * 2), (255, 255, 255, 0)
    )
    draw = ImageDraw.Draw(right)
    draw.text(
        (0, 0),
        rtext,
        font=FONT,
        fill=gray,
        stroke_width=5,
        stroke_fill=white,
    )
    right = right.transform(
        right.size, Image.Transform.AFFINE, data, Image.Resampling.BICUBIC
    )
    right = right.crop(right.getbbox())
    target = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(target)
    target.paste(left, (10, FONTSIZE), left)
    draw.bitmap((left.size[0] - dx, dy), HALO, fill=gray)
    target.paste(right, (left.size[0], FONTSIZE - 6), right)  # magic number dkw just -6
    target.paste(image, (left.size[0] - dx, dy), image)
    target = target.crop(target.getbbox())
    return target.convert("RGB")


@cmd.handle()
async def _(state: T_State):
    try:
        ltext, rtext = state["_args"].ltext, state["_args"].rtext
        message = img_to_segment(draw(ltext, rtext))
    except Exception as e:
        sv.logger.error(f"draw ba pics error:{e}")
    await cmd.finish(message)