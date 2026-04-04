#!/usr/bin/env python3
"""
JINXUS Pixel Art Character Spritesheet Generator
Generates 7 character spritesheets (112x96 each) for the pixel office.

Layout per sheet:
  7 columns (frames) x 3 rows (directions)
  Each frame: 16x32 pixels
  Row 0: DOWN, Row 1: UP, Row 2: RIGHT

Frames: walk0, walk1, walk2, type0, type1, read0, read1
"""

from PIL import Image
import os

OUTPUT_DIR = "/home/jinsookim/jinxus/frontend/public/pixel-agents/characters"
FRAME_W, FRAME_H = 16, 32
COLS, ROWS = 7, 3
SHEET_W, SHEET_H = FRAME_W * COLS, FRAME_H * ROWS

T = (0, 0, 0, 0)  # Transparent


def rgba(r, g, b, a=255):
    return (r, g, b, a)


# ── Color Palettes ──────────────────────────────────────────────

SKIN_LIGHT = rgba(255, 220, 185)
SKIN_LIGHT_SHADOW = rgba(230, 195, 160)
SKIN_MED = rgba(240, 200, 160)
SKIN_MED_SHADOW = rgba(215, 175, 135)
SKIN_TAN = rgba(200, 160, 120)
SKIN_TAN_SHADOW = rgba(175, 135, 100)

EYE_WHITE = rgba(255, 255, 255)
EYE_BLACK = rgba(30, 30, 40)
EYE_HIGHLIGHT = rgba(255, 255, 255)
MOUTH = rgba(200, 100, 100)

SHADOW_GROUND = rgba(0, 0, 0, 60)

# Character-specific palettes
PALETTES = {
    "char_0": {
        "skin": SKIN_LIGHT, "skin_s": SKIN_LIGHT_SHADOW,
        "hair": rgba(50, 40, 35), "hair_s": rgba(35, 28, 24),
        "shirt": rgba(80, 130, 200), "shirt_s": rgba(60, 100, 165),
        "pants": rgba(195, 180, 140), "pants_s": rgba(165, 150, 115),
        "shoes": rgba(80, 65, 50), "shoes_s": rgba(55, 45, 35),
        "belt": rgba(90, 75, 60),
        "collar": rgba(240, 240, 245),
    },
    "char_1": {
        "skin": SKIN_LIGHT, "skin_s": SKIN_LIGHT_SHADOW,
        "hair": rgba(60, 45, 35), "hair_s": rgba(40, 30, 22),
        "shirt": rgba(130, 210, 200), "shirt_s": rgba(100, 180, 170),
        "pants": rgba(55, 60, 75), "pants_s": rgba(40, 44, 55),
        "shoes": rgba(240, 240, 240), "shoes_s": rgba(200, 200, 200),
        "belt": rgba(55, 60, 75),
        "collar": rgba(130, 210, 200),
        "hood": rgba(110, 190, 180),
    },
    "char_2": {
        "skin": SKIN_TAN, "skin_s": SKIN_TAN_SHADOW,
        "hair": rgba(45, 35, 25), "hair_s": rgba(30, 22, 16),
        "shirt": rgba(240, 150, 50), "shirt_s": rgba(210, 125, 35),
        "pants": rgba(50, 50, 55), "pants_s": rgba(35, 35, 40),
        "shoes": rgba(200, 60, 60), "shoes_s": rgba(160, 45, 45),
        "belt": rgba(70, 60, 50),
        "collar": rgba(240, 150, 50),
    },
    "char_3": {
        "skin": SKIN_LIGHT, "skin_s": SKIN_LIGHT_SHADOW,
        "hair": rgba(50, 35, 30), "hair_s": rgba(35, 24, 20),
        "shirt": rgba(190, 170, 220), "shirt_s": rgba(160, 140, 190),
        "pants": rgba(40, 40, 45), "pants_s": rgba(28, 28, 32),
        "shoes": rgba(30, 30, 35), "shoes_s": rgba(20, 20, 25),
        "belt": rgba(40, 40, 45),
        "collar": rgba(220, 200, 240),
        "skirt": True,
    },
    "char_4": {
        "skin": SKIN_MED, "skin_s": SKIN_MED_SHADOW,
        "hair": rgba(40, 35, 30), "hair_s": rgba(25, 22, 18),
        "shirt": rgba(30, 40, 70), "shirt_s": rgba(20, 28, 50),
        "shirt_inner": rgba(240, 240, 245),
        "pants": rgba(140, 140, 150), "pants_s": rgba(110, 110, 120),
        "shoes": rgba(40, 35, 30), "shoes_s": rgba(25, 22, 18),
        "belt": rgba(50, 45, 40),
        "collar": rgba(240, 240, 245),
        "tie": rgba(160, 50, 50),
    },
    "char_5": {
        "skin": SKIN_MED, "skin_s": SKIN_MED_SHADOW,
        "hair": rgba(35, 25, 20), "hair_s": rgba(22, 16, 12),
        "shirt": rgba(200, 60, 60), "shirt_s": rgba(170, 45, 45),
        "shirt_inner": rgba(240, 235, 225),
        "pants": rgba(50, 50, 55), "pants_s": rgba(35, 35, 40),
        "shoes": rgba(60, 50, 40), "shoes_s": rgba(40, 33, 26),
        "belt": rgba(60, 50, 40),
        "collar": rgba(240, 235, 225),
        "chopstick": rgba(200, 180, 140),
    },
    "char_core": {
        "skin": SKIN_LIGHT, "skin_s": SKIN_LIGHT_SHADOW,
        "hair": rgba(180, 185, 195), "hair_s": rgba(150, 155, 165),
        "shirt": rgba(25, 25, 30), "shirt_s": rgba(15, 15, 18),
        "pants": rgba(25, 25, 30), "pants_s": rgba(15, 15, 18),
        "shoes": rgba(20, 18, 15), "shoes_s": rgba(10, 9, 8),
        "belt": rgba(25, 25, 30),
        "collar": rgba(245, 245, 250),
        "tie": rgba(210, 180, 50),
        "tie_s": rgba(180, 150, 35),
    },
}


class SpriteDrawer:
    """Draws a single 16x32 frame onto an image at a given offset."""

    def __init__(self, img, ox, oy, pal):
        self.img = img
        self.ox = ox
        self.oy = oy
        self.p = pal

    def px(self, x, y, color):
        if color == T or color is None:
            return
        if 0 <= x < FRAME_W and 0 <= y < FRAME_H:
            self.img.putpixel((self.ox + x, self.oy + y), color)

    def rect(self, x, y, w, h, color):
        for dy in range(h):
            for dx in range(w):
                self.px(x + dx, y + dy, color)

    def hline(self, x, y, length, color):
        for i in range(length):
            self.px(x + i, y, color)

    def draw_face_down(self):
        """Draw face facing down (toward viewer)."""
        p = self.p
        skin, skin_s = p["skin"], p["skin_s"]

        # Eyes: 2x2 each, with 1px highlight
        # Left eye at (4,5), right eye at (10,5)
        self.rect(4, 5, 2, 2, EYE_BLACK)
        self.px(4, 5, EYE_HIGHLIGHT)  # highlight top-left
        self.rect(10, 5, 2, 2, EYE_BLACK)
        self.px(10, 5, EYE_HIGHLIGHT)

        # Nose hint
        self.px(7, 7, skin_s)
        self.px(8, 7, skin_s)

        # Mouth
        self.px(7, 8, MOUTH)
        self.px(8, 8, MOUTH)

        # Forehead skin
        self.hline(4, 3, 8, skin)
        self.hline(4, 4, 8, skin)

        # Face sides
        self.hline(3, 5, 1, skin)
        self.hline(12, 5, 1, skin)
        self.hline(3, 6, 1, skin)
        self.hline(12, 6, 1, skin)

        # Cheeks
        self.hline(3, 7, 1, skin)
        self.hline(12, 7, 1, skin)
        self.hline(3, 8, 1, skin)
        self.hline(12, 8, 1, skin)

        # Jaw / chin
        self.hline(4, 9, 8, skin)
        self.hline(5, 10, 6, skin_s)  # chin shadow

    def draw_face_up(self):
        """Draw face facing up (away from viewer) - back of head."""
        p = self.p
        # No face features visible, just hair/skin at neck
        skin_s = p["skin_s"]
        self.hline(5, 9, 6, skin_s)  # neck visible

    def draw_face_right(self):
        """Draw face facing right (profile)."""
        p = self.p
        skin, skin_s = p["skin"], p["skin_s"]

        # Profile face - shifted right
        self.hline(7, 3, 5, skin)
        self.hline(7, 4, 5, skin)
        self.hline(7, 5, 5, skin)
        self.hline(7, 6, 5, skin)
        self.hline(7, 7, 6, skin)  # nose protrusion
        self.hline(7, 8, 5, skin)
        self.hline(8, 9, 4, skin)
        self.px(12, 7, skin_s)  # nose tip shadow

        # Eye (one visible) at (10, 5)
        self.rect(10, 5, 2, 2, EYE_BLACK)
        self.px(10, 5, EYE_HIGHLIGHT)

        # Mouth
        self.px(10, 8, MOUTH)

    def draw_neck(self, direction):
        """Neck below head."""
        p = self.p
        if direction == "down":
            self.px(7, 10, p["skin"])
            self.px(8, 10, p["skin"])
        elif direction == "up":
            self.px(7, 10, p["skin_s"])
            self.px(8, 10, p["skin_s"])
        else:  # right
            self.px(9, 10, p["skin"])
            self.px(10, 10, p["skin"])


def draw_hair_char0(d, direction):
    """Short dark hair - new developer."""
    h, hs = d.p["hair"], d.p["hair_s"]
    if direction == "down":
        d.hline(4, 0, 8, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 10, h)
        d.hline(3, 3, 1, h)  # side
        d.hline(12, 3, 1, h)
        d.hline(3, 4, 1, hs)
        d.hline(12, 4, 1, hs)
    elif direction == "up":
        d.hline(4, 0, 8, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 10, h)
        d.hline(3, 3, 10, h)
        d.hline(3, 4, 10, h)
        d.hline(3, 5, 10, hs)
        d.hline(3, 6, 10, hs)
        d.hline(4, 7, 8, hs)
        d.hline(4, 8, 8, h)
    else:  # right
        d.hline(5, 0, 7, h)
        d.hline(4, 1, 8, h)
        d.hline(4, 2, 9, h)
        d.hline(5, 3, 2, h)  # forehead exposed right
        d.hline(5, 4, 2, hs)


def draw_hair_char1(d, direction):
    """Long ponytail - senior engineer."""
    h, hs = d.p["hair"], d.p["hair_s"]
    if direction == "down":
        d.hline(4, 0, 8, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 10, h)
        d.hline(3, 3, 1, h)
        d.hline(12, 3, 1, h)
        # Side hair hanging down
        d.hline(2, 4, 2, h)
        d.hline(12, 4, 2, h)
        d.hline(2, 5, 1, hs)
        d.hline(13, 5, 1, hs)
        d.hline(2, 6, 1, hs)
        d.hline(13, 6, 1, hs)
    elif direction == "up":
        d.hline(4, 0, 8, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 10, h)
        d.hline(3, 3, 10, h)
        d.hline(3, 4, 10, h)
        d.hline(4, 5, 8, hs)
        d.hline(5, 6, 6, hs)
        # Ponytail going down the back
        d.hline(7, 7, 3, h)
        d.hline(7, 8, 3, h)
        d.hline(7, 9, 2, h)
        d.hline(7, 10, 2, hs)
        d.hline(7, 11, 2, hs)
        d.hline(8, 12, 1, hs)
    else:  # right
        d.hline(5, 0, 7, h)
        d.hline(4, 1, 9, h)
        d.hline(4, 2, 9, h)
        d.hline(5, 3, 2, h)
        d.hline(4, 4, 2, hs)
        # Ponytail trailing behind (left side)
        d.hline(3, 5, 3, h)
        d.hline(2, 6, 3, h)
        d.hline(2, 7, 2, hs)
        d.hline(1, 8, 2, hs)


def draw_hair_char2(d, direction):
    """Curly/afro hair - designer."""
    h, hs = d.p["hair"], d.p["hair_s"]
    if direction == "down":
        d.hline(4, 0, 9, h)
        d.hline(3, 1, 11, h)
        d.hline(2, 2, 12, h)
        d.hline(2, 3, 2, h)
        d.hline(12, 3, 2, h)
        d.hline(2, 4, 1, hs)
        d.hline(13, 4, 1, hs)
        # Top volume
        d.px(5, 0, hs)
        d.px(9, 0, hs)
        d.px(11, 0, hs)
    elif direction == "up":
        d.hline(4, 0, 9, h)
        d.hline(3, 1, 11, h)
        d.hline(2, 2, 12, h)
        d.hline(2, 3, 12, h)
        d.hline(2, 4, 12, h)
        d.hline(3, 5, 10, hs)
        d.hline(3, 6, 10, hs)
        d.hline(4, 7, 8, hs)
        d.px(5, 1, hs)
        d.px(10, 2, hs)
    else:  # right
        d.hline(4, 0, 9, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 11, h)
        d.hline(4, 3, 3, h)
        d.hline(3, 4, 3, hs)
        d.px(6, 0, hs)
        d.px(10, 1, hs)


def draw_hair_char3(d, direction):
    """Bob cut - PM."""
    h, hs = d.p["hair"], d.p["hair_s"]
    if direction == "down":
        d.hline(4, 0, 8, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 10, h)
        d.hline(3, 3, 1, h)
        d.hline(12, 3, 1, h)
        # Bob sides
        d.hline(2, 4, 2, h)
        d.hline(12, 4, 2, h)
        d.hline(2, 5, 2, h)
        d.hline(12, 5, 2, h)
        d.hline(2, 6, 2, hs)
        d.hline(12, 6, 2, hs)
        d.hline(3, 7, 1, hs)
        d.hline(12, 7, 1, hs)
    elif direction == "up":
        d.hline(4, 0, 8, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 10, h)
        d.hline(2, 3, 12, h)
        d.hline(2, 4, 12, h)
        d.hline(2, 5, 12, hs)
        d.hline(2, 6, 12, hs)
        d.hline(3, 7, 10, hs)
        d.hline(4, 8, 8, h)
    else:  # right
        d.hline(5, 0, 7, h)
        d.hline(4, 1, 9, h)
        d.hline(4, 2, 9, h)
        d.hline(5, 3, 2, h)
        d.hline(4, 4, 3, h)
        d.hline(4, 5, 3, hs)
        d.hline(4, 6, 2, hs)


def draw_hair_char4(d, direction):
    """Spiky styled hair - team lead."""
    h, hs = d.p["hair"], d.p["hair_s"]
    if direction == "down":
        # Spiky top
        d.px(5, 0, h)
        d.px(8, 0, h)
        d.px(11, 0, h)
        d.hline(4, 1, 9, h)
        d.hline(3, 2, 10, h)
        d.hline(3, 3, 1, h)
        d.hline(12, 3, 1, h)
        d.hline(3, 4, 1, hs)
        d.hline(12, 4, 1, hs)
    elif direction == "up":
        d.px(5, 0, h)
        d.px(8, 0, h)
        d.px(11, 0, h)
        d.hline(4, 1, 9, h)
        d.hline(3, 2, 10, h)
        d.hline(3, 3, 10, h)
        d.hline(3, 4, 10, h)
        d.hline(4, 5, 8, hs)
        d.hline(5, 6, 6, hs)
    else:  # right
        d.px(6, 0, h)
        d.px(9, 0, h)
        d.px(12, 0, h)
        d.hline(5, 1, 8, h)
        d.hline(4, 2, 9, h)
        d.hline(5, 3, 2, h)
        d.hline(5, 4, 1, hs)


def draw_hair_char5(d, direction):
    """Bun hair with chopsticks - data analyst."""
    h, hs = d.p["hair"], d.p["hair_s"]
    cs = d.p.get("chopstick", rgba(200, 180, 140))
    if direction == "down":
        # Bun on top
        d.hline(6, 0, 4, h)
        d.hline(5, 1, 6, h)
        d.hline(5, 1, 1, hs)
        # Chopsticks sticking out
        d.px(4, 0, cs)
        d.px(3, 0, cs)
        d.px(12, 0, cs)
        d.px(11, 1, cs)
        # Main hair
        d.hline(4, 2, 8, h)
        d.hline(3, 3, 10, h)
        d.hline(3, 4, 1, h)
        d.hline(12, 4, 1, h)
        d.hline(3, 5, 1, hs)
        d.hline(12, 5, 1, hs)
    elif direction == "up":
        d.hline(6, 0, 4, h)
        d.hline(5, 1, 6, h)
        d.px(4, 0, cs)
        d.px(12, 0, cs)
        d.hline(4, 2, 8, h)
        d.hline(3, 3, 10, h)
        d.hline(3, 4, 10, h)
        d.hline(3, 5, 10, hs)
        d.hline(4, 6, 8, hs)
        d.hline(5, 7, 6, h)
    else:  # right
        d.hline(7, 0, 4, h)
        d.hline(6, 1, 5, h)
        d.px(5, 0, cs)
        d.px(12, 0, cs)
        d.hline(5, 2, 7, h)
        d.hline(5, 3, 3, h)
        d.hline(5, 4, 2, hs)


def draw_hair_core(d, direction):
    """Slicked back silver hair - CEO."""
    h, hs = d.p["hair"], d.p["hair_s"]
    if direction == "down":
        d.hline(4, 0, 8, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 10, hs)
        d.hline(3, 3, 1, hs)
        d.hline(12, 3, 1, hs)
    elif direction == "up":
        d.hline(4, 0, 8, h)
        d.hline(3, 1, 10, h)
        d.hline(3, 2, 10, h)
        d.hline(3, 3, 10, hs)
        d.hline(3, 4, 10, hs)
        d.hline(4, 5, 8, hs)
        d.hline(5, 6, 6, h)
    else:  # right
        d.hline(5, 0, 7, h)
        d.hline(4, 1, 9, h)
        d.hline(4, 2, 9, hs)
        d.hline(5, 3, 2, hs)


HAIR_FUNCS = {
    "char_0": draw_hair_char0,
    "char_1": draw_hair_char1,
    "char_2": draw_hair_char2,
    "char_3": draw_hair_char3,
    "char_4": draw_hair_char4,
    "char_5": draw_hair_char5,
    "char_core": draw_hair_core,
}


def draw_body_down(d, char_id, frame):
    """Draw torso, arms, legs facing down."""
    p = d.p
    shirt, shirt_s = p["shirt"], p["shirt_s"]
    pants, pants_s = p["pants"], p["pants_s"]
    shoes, shoes_s = p["shoes"], p["shoes_s"]
    belt = p["belt"]
    collar = p.get("collar", shirt)
    is_skirt = p.get("skirt", False)
    has_tie = "tie" in p
    has_blazer = "shirt_inner" in p and char_id == "char_4"
    has_cardigan = "shirt_inner" in p and char_id == "char_5"

    # ── Shoulders & collar (rows 11-12) ──
    d.hline(4, 11, 8, collar)
    if has_tie:
        d.px(7, 11, p["tie"])
        d.px(8, 11, p["tie"])

    # ── Torso rows 12-17 ──
    if frame in ("walk0", "walk1", "walk2"):
        # Walking/standing body
        d.hline(3, 12, 10, shirt)
        d.hline(3, 13, 10, shirt)
        d.hline(3, 14, 10, shirt)
        d.hline(4, 15, 8, shirt)
        d.hline(4, 16, 8, shirt_s)
        d.hline(4, 17, 8, shirt_s)

        if has_blazer:
            inner = p["shirt_inner"]
            for row in range(12, 17):
                d.px(7, row, inner)
                d.px(8, row, inner)
            d.px(7, 12, p["tie"])
            d.px(8, 13, p["tie"])
            d.px(7, 14, p["tie"])
            d.px(8, 15, p["tie"])

        if has_cardigan:
            inner = p["shirt_inner"]
            d.px(7, 12, inner)
            d.px(8, 12, inner)
            d.px(7, 13, inner)
            d.px(8, 13, inner)

        if has_tie and not has_blazer:
            d.px(7, 12, p["tie"])
            d.px(8, 12, p.get("tie_s", p["tie"]))
            d.px(7, 13, p.get("tie_s", p["tie"]))
            d.px(8, 13, p["tie"])
            d.px(7, 14, p["tie"])
            d.px(8, 14, p.get("tie_s", p["tie"]))
            d.px(7, 15, p.get("tie_s", p["tie"]))

        # Arms (sides of torso)
        if frame == "walk0":
            # Standing - arms at sides
            d.px(2, 12, shirt)
            d.px(13, 12, shirt)
            d.px(2, 13, shirt_s)
            d.px(13, 13, shirt_s)
            d.px(2, 14, p["skin"])
            d.px(13, 14, p["skin"])
            d.px(2, 15, p["skin_s"])
            d.px(13, 15, p["skin_s"])
        elif frame == "walk1":
            # Left foot fwd, right arm fwd
            d.px(2, 12, shirt)
            d.px(13, 12, shirt)
            d.px(2, 13, shirt_s)
            d.px(13, 11, shirt_s)  # right arm up/forward
            d.px(2, 14, p["skin"])
            d.px(13, 12, p["skin"])
            d.px(2, 15, p["skin_s"])
        elif frame == "walk2":
            # Right foot fwd, left arm fwd
            d.px(2, 11, shirt)  # left arm up/forward
            d.px(13, 12, shirt)
            d.px(2, 12, shirt_s)
            d.px(13, 13, shirt_s)
            d.px(2, 12, p["skin"])
            d.px(13, 14, p["skin"])
            d.px(13, 15, p["skin_s"])

    elif frame in ("type0", "type1"):
        # Sitting typing - torso shorter, arms forward
        d.hline(3, 12, 10, shirt)
        d.hline(3, 13, 10, shirt)
        d.hline(4, 14, 8, shirt)
        d.hline(4, 15, 8, shirt_s)
        d.hline(4, 16, 8, shirt_s)

        if has_tie and not has_blazer:
            d.px(7, 12, p["tie"])
            d.px(8, 13, p["tie"])

        # Arms forward (typing)
        if frame == "type0":
            d.px(3, 14, p["skin"])
            d.px(12, 14, p["skin"])
            d.hline(3, 15, 2, p["skin_s"])
            d.hline(11, 15, 2, p["skin_s"])
        else:
            d.px(3, 14, p["skin"])
            d.px(12, 14, p["skin_s"])
            d.hline(3, 15, 2, p["skin"])
            d.hline(11, 15, 2, p["skin_s"])

    elif frame in ("read0", "read1"):
        # Standing, one arm up holding document
        d.hline(3, 12, 10, shirt)
        d.hline(3, 13, 10, shirt)
        d.hline(3, 14, 10, shirt)
        d.hline(4, 15, 8, shirt)
        d.hline(4, 16, 8, shirt_s)
        d.hline(4, 17, 8, shirt_s)

        if has_tie and not has_blazer:
            d.px(7, 12, p["tie"])
            d.px(8, 13, p["tie"])

        # Right arm at side
        d.px(13, 12, shirt)
        d.px(13, 13, shirt_s)
        d.px(13, 14, p["skin"])

        # Left arm up (holding doc)
        if frame == "read0":
            d.px(2, 11, shirt)
            d.px(1, 10, p["skin"])
            d.px(1, 9, p["skin_s"])
            # Document
            d.px(0, 8, rgba(240, 240, 240))
            d.px(1, 8, rgba(240, 240, 240))
            d.px(0, 7, rgba(240, 240, 240))
            d.px(1, 7, rgba(220, 220, 220))
        else:
            d.px(2, 11, shirt)
            d.px(1, 10, p["skin"])
            d.px(1, 9, p["skin"])
            d.px(0, 8, rgba(240, 240, 240))
            d.px(1, 8, rgba(240, 240, 240))
            d.px(0, 9, rgba(220, 220, 220))

    # ── Belt/waist (rows 18-19) ──
    if frame in ("type0", "type1"):
        d.hline(4, 17, 8, belt)
        # Sitting - no visible legs below lap
        d.hline(3, 18, 10, pants)
        d.hline(3, 19, 10, pants_s)
        # Chair implied - no legs visible below
        return
    else:
        d.hline(4, 18, 8, belt)

    # ── Legs (rows 19-26) ──
    if is_skirt:
        # Skirt instead of pants
        d.hline(4, 19, 8, pants)
        d.hline(3, 20, 10, pants)
        d.hline(3, 21, 10, pants)
        d.hline(4, 22, 8, pants_s)
        d.hline(4, 23, 8, pants_s)
        # Legs below skirt
        d.hline(5, 24, 2, p["skin"])
        d.hline(9, 24, 2, p["skin"])
        d.hline(5, 25, 2, p["skin_s"])
        d.hline(9, 25, 2, p["skin_s"])
        if frame == "walk1":
            d.hline(4, 24, 2, p["skin"])
            d.hline(10, 24, 2, p["skin"])
        elif frame == "walk2":
            d.hline(6, 24, 2, p["skin"])
            d.hline(8, 24, 2, p["skin"])
    else:
        if frame == "walk0":
            # Standing
            d.hline(5, 19, 2, pants)
            d.hline(9, 19, 2, pants)
            d.hline(5, 20, 2, pants)
            d.hline(9, 20, 2, pants)
            d.hline(5, 21, 2, pants)
            d.hline(9, 21, 2, pants)
            d.hline(5, 22, 2, pants_s)
            d.hline(9, 22, 2, pants_s)
            d.hline(5, 23, 2, pants_s)
            d.hline(9, 23, 2, pants_s)
            d.hline(5, 24, 2, pants_s)
            d.hline(9, 24, 2, pants_s)
        elif frame == "walk1":
            # Left leg forward
            d.hline(4, 19, 2, pants)
            d.hline(9, 19, 2, pants)
            d.hline(4, 20, 2, pants)
            d.hline(10, 20, 2, pants)
            d.hline(4, 21, 2, pants)
            d.hline(10, 21, 2, pants)
            d.hline(4, 22, 2, pants_s)
            d.hline(10, 22, 2, pants_s)
            d.hline(4, 23, 2, pants_s)
            d.hline(10, 23, 2, pants_s)
            d.hline(4, 24, 2, pants_s)
            d.hline(10, 24, 2, pants_s)
        elif frame == "walk2":
            # Right leg forward
            d.hline(5, 19, 2, pants)
            d.hline(10, 19, 2, pants)
            d.hline(6, 20, 2, pants)
            d.hline(10, 20, 2, pants)
            d.hline(6, 21, 2, pants)
            d.hline(10, 21, 2, pants)
            d.hline(6, 22, 2, pants_s)
            d.hline(10, 22, 2, pants_s)
            d.hline(6, 23, 2, pants_s)
            d.hline(10, 23, 2, pants_s)
            d.hline(6, 24, 2, pants_s)
            d.hline(10, 24, 2, pants_s)
        else:
            # read frames - standing legs
            d.hline(5, 19, 2, pants)
            d.hline(9, 19, 2, pants)
            d.hline(5, 20, 2, pants)
            d.hline(9, 20, 2, pants)
            d.hline(5, 21, 2, pants)
            d.hline(9, 21, 2, pants)
            d.hline(5, 22, 2, pants_s)
            d.hline(9, 22, 2, pants_s)
            d.hline(5, 23, 2, pants_s)
            d.hline(9, 23, 2, pants_s)
            d.hline(5, 24, 2, pants_s)
            d.hline(9, 24, 2, pants_s)

    # ── Shoes (rows 25-27) ──
    if frame in ("walk1",):
        d.hline(3, 25, 3, shoes)
        d.hline(10, 25, 3, shoes)
        d.hline(3, 26, 3, shoes_s)
        d.hline(10, 26, 3, shoes_s)
        d.hline(3, 27, 3, shoes)
        d.hline(10, 27, 3, shoes)
    elif frame in ("walk2",):
        d.hline(5, 25, 3, shoes)
        d.hline(9, 25, 3, shoes)
        d.hline(5, 26, 3, shoes_s)
        d.hline(9, 26, 3, shoes_s)
        d.hline(5, 27, 3, shoes)
        d.hline(9, 27, 3, shoes)
    else:
        d.hline(4, 25, 3, shoes)
        d.hline(9, 25, 3, shoes)
        d.hline(4, 26, 3, shoes_s)
        d.hline(9, 26, 3, shoes_s)
        d.hline(4, 27, 3, shoes)
        d.hline(9, 27, 3, shoes)

    if is_skirt:
        # Adjust shoe position for skirt characters
        pass

    # ── Ground shadow ──
    d.hline(3, 29, 10, SHADOW_GROUND)
    d.hline(4, 30, 8, SHADOW_GROUND)


def draw_body_up(d, char_id, frame):
    """Draw torso, arms, legs facing up (back view)."""
    p = d.p
    shirt, shirt_s = p["shirt"], p["shirt_s"]
    pants, pants_s = p["pants"], p["pants_s"]
    shoes, shoes_s = p["shoes"], p["shoes_s"]
    belt = p["belt"]
    is_skirt = p.get("skirt", False)

    # ── Shoulders (rows 11-12) ──
    d.hline(4, 11, 8, shirt)

    # ── Torso rows 12-17 ──
    if frame in ("walk0", "walk1", "walk2", "read0", "read1"):
        d.hline(3, 12, 10, shirt)
        d.hline(3, 13, 10, shirt)
        d.hline(3, 14, 10, shirt_s)
        d.hline(4, 15, 8, shirt_s)
        d.hline(4, 16, 8, shirt_s)
        d.hline(4, 17, 8, shirt)

        if frame == "walk0":
            d.px(2, 12, shirt)
            d.px(13, 12, shirt)
            d.px(2, 13, shirt_s)
            d.px(13, 13, shirt_s)
            d.px(2, 14, p["skin"])
            d.px(13, 14, p["skin"])
        elif frame == "walk1":
            d.px(2, 13, shirt)
            d.px(13, 11, shirt)
            d.px(2, 14, p["skin"])
            d.px(13, 12, p["skin"])
        elif frame == "walk2":
            d.px(2, 11, shirt)
            d.px(13, 13, shirt)
            d.px(2, 12, p["skin"])
            d.px(13, 14, p["skin"])
        elif frame == "read0":
            d.px(13, 12, shirt)
            d.px(13, 13, shirt_s)
            d.px(13, 14, p["skin"])
            d.px(2, 11, shirt)
            d.px(1, 10, p["skin"])
            d.px(1, 9, p["skin_s"])
        elif frame == "read1":
            d.px(13, 12, shirt)
            d.px(13, 13, shirt_s)
            d.px(13, 14, p["skin"])
            d.px(2, 11, shirt)
            d.px(1, 10, p["skin"])
            d.px(1, 11, p["skin_s"])

    elif frame in ("type0", "type1"):
        d.hline(3, 12, 10, shirt)
        d.hline(3, 13, 10, shirt)
        d.hline(4, 14, 8, shirt_s)
        d.hline(4, 15, 8, shirt_s)
        d.hline(4, 16, 8, shirt)
        # Arms forward
        d.px(3, 14, p["skin"])
        d.px(12, 14, p["skin"])
        d.hline(3, 15, 2, p["skin_s"])
        d.hline(11, 15, 2, p["skin_s"])
        d.hline(4, 17, 8, belt)
        d.hline(3, 18, 10, pants)
        d.hline(3, 19, 10, pants_s)
        return

    # Belt
    d.hline(4, 18, 8, belt)

    # Legs
    if is_skirt:
        d.hline(4, 19, 8, pants)
        d.hline(3, 20, 10, pants)
        d.hline(3, 21, 10, pants)
        d.hline(4, 22, 8, pants_s)
        d.hline(4, 23, 8, pants_s)
        d.hline(5, 24, 2, p["skin"])
        d.hline(9, 24, 2, p["skin"])
        d.hline(5, 25, 2, p["skin_s"])
        d.hline(9, 25, 2, p["skin_s"])
    else:
        if frame == "walk1":
            d.hline(4, 19, 2, pants)
            d.hline(9, 19, 2, pants)
            d.hline(4, 20, 2, pants)
            d.hline(10, 20, 2, pants)
            d.hline(4, 21, 2, pants)
            d.hline(10, 21, 2, pants_s)
            d.hline(4, 22, 2, pants_s)
            d.hline(10, 22, 2, pants_s)
            d.hline(4, 23, 2, pants_s)
            d.hline(10, 23, 2, pants_s)
            d.hline(4, 24, 2, pants_s)
            d.hline(10, 24, 2, pants_s)
        elif frame == "walk2":
            d.hline(5, 19, 2, pants)
            d.hline(10, 19, 2, pants)
            d.hline(6, 20, 2, pants)
            d.hline(10, 20, 2, pants)
            d.hline(6, 21, 2, pants_s)
            d.hline(10, 21, 2, pants)
            d.hline(6, 22, 2, pants_s)
            d.hline(10, 22, 2, pants_s)
            d.hline(6, 23, 2, pants_s)
            d.hline(10, 23, 2, pants_s)
            d.hline(6, 24, 2, pants_s)
            d.hline(10, 24, 2, pants_s)
        else:
            d.hline(5, 19, 2, pants)
            d.hline(9, 19, 2, pants)
            d.hline(5, 20, 2, pants)
            d.hline(9, 20, 2, pants)
            d.hline(5, 21, 2, pants)
            d.hline(9, 21, 2, pants)
            d.hline(5, 22, 2, pants_s)
            d.hline(9, 22, 2, pants_s)
            d.hline(5, 23, 2, pants_s)
            d.hline(9, 23, 2, pants_s)
            d.hline(5, 24, 2, pants_s)
            d.hline(9, 24, 2, pants_s)

    # Shoes
    if frame == "walk1":
        d.hline(3, 25, 3, shoes)
        d.hline(10, 25, 3, shoes)
        d.hline(3, 26, 3, shoes_s)
        d.hline(10, 26, 3, shoes_s)
        d.hline(3, 27, 3, shoes)
        d.hline(10, 27, 3, shoes)
    elif frame == "walk2":
        d.hline(5, 25, 3, shoes)
        d.hline(9, 25, 3, shoes)
        d.hline(5, 26, 3, shoes_s)
        d.hline(9, 26, 3, shoes_s)
        d.hline(5, 27, 3, shoes)
        d.hline(9, 27, 3, shoes)
    else:
        d.hline(4, 25, 3, shoes)
        d.hline(9, 25, 3, shoes)
        d.hline(4, 26, 3, shoes_s)
        d.hline(9, 26, 3, shoes_s)
        d.hline(4, 27, 3, shoes)
        d.hline(9, 27, 3, shoes)

    d.hline(3, 29, 10, SHADOW_GROUND)
    d.hline(4, 30, 8, SHADOW_GROUND)


def draw_body_right(d, char_id, frame):
    """Draw torso, arms, legs facing right (profile)."""
    p = d.p
    shirt, shirt_s = p["shirt"], p["shirt_s"]
    pants, pants_s = p["pants"], p["pants_s"]
    shoes, shoes_s = p["shoes"], p["shoes_s"]
    belt = p["belt"]
    is_skirt = p.get("skirt", False)
    has_tie = "tie" in p

    # Shoulders
    d.hline(5, 11, 7, shirt)

    # Torso (profile - narrower)
    if frame in ("walk0", "walk1", "walk2", "read0", "read1"):
        d.hline(5, 12, 7, shirt)
        d.hline(5, 13, 7, shirt)
        d.hline(5, 14, 7, shirt_s)
        d.hline(6, 15, 6, shirt_s)
        d.hline(6, 16, 6, shirt)
        d.hline(6, 17, 6, shirt)

        if has_tie:
            d.px(11, 12, p["tie"])
            d.px(11, 13, p.get("tie_s", p["tie"]))
            d.px(11, 14, p["tie"])

        # Arm
        if frame == "walk0":
            d.px(12, 12, shirt)
            d.px(12, 13, shirt_s)
            d.px(12, 14, p["skin"])
            d.px(12, 15, p["skin_s"])
        elif frame == "walk1":
            # Arm forward
            d.px(12, 11, shirt)
            d.px(13, 12, p["skin"])
            d.px(13, 13, p["skin_s"])
        elif frame == "walk2":
            # Arm back
            d.px(4, 13, shirt)
            d.px(4, 14, p["skin"])
            d.px(4, 15, p["skin_s"])
        elif frame == "read0":
            # Arm up holding doc
            d.px(12, 11, shirt)
            d.px(13, 10, p["skin"])
            d.px(13, 9, p["skin_s"])
            d.px(14, 8, rgba(240, 240, 240))
            d.px(14, 7, rgba(240, 240, 240))
            d.px(13, 8, rgba(220, 220, 220))
        elif frame == "read1":
            d.px(12, 11, shirt)
            d.px(13, 10, p["skin"])
            d.px(13, 9, p["skin"])
            d.px(14, 8, rgba(240, 240, 240))
            d.px(14, 9, rgba(220, 220, 220))

    elif frame in ("type0", "type1"):
        d.hline(5, 12, 7, shirt)
        d.hline(5, 13, 7, shirt)
        d.hline(6, 14, 6, shirt_s)
        d.hline(6, 15, 6, shirt_s)
        d.hline(6, 16, 6, shirt)
        # Arms forward
        d.px(12, 13, p["skin"])
        d.px(13, 14, p["skin_s"])
        if frame == "type1":
            d.px(13, 13, p["skin"])
        d.hline(6, 17, 6, belt)
        d.hline(5, 18, 7, pants)
        d.hline(5, 19, 7, pants_s)
        return

    # Belt
    d.hline(6, 18, 6, belt)

    # Legs (profile)
    if is_skirt:
        d.hline(5, 19, 7, pants)
        d.hline(5, 20, 8, pants)
        d.hline(5, 21, 8, pants)
        d.hline(6, 22, 6, pants_s)
        d.hline(6, 23, 6, pants_s)
        d.hline(7, 24, 2, p["skin"])
        d.hline(7, 25, 2, p["skin_s"])
    else:
        if frame == "walk0":
            d.hline(7, 19, 3, pants)
            d.hline(7, 20, 3, pants)
            d.hline(7, 21, 3, pants)
            d.hline(7, 22, 3, pants_s)
            d.hline(7, 23, 3, pants_s)
            d.hline(7, 24, 3, pants_s)
        elif frame == "walk1":
            # One leg forward, one back
            d.hline(9, 19, 3, pants)
            d.hline(6, 19, 2, pants)
            d.hline(9, 20, 3, pants)
            d.hline(5, 20, 2, pants)
            d.hline(10, 21, 2, pants_s)
            d.hline(5, 21, 2, pants_s)
            d.hline(10, 22, 2, pants_s)
            d.hline(5, 22, 2, pants_s)
            d.hline(10, 23, 2, pants_s)
            d.hline(5, 23, 2, pants_s)
            d.hline(10, 24, 2, pants_s)
            d.hline(5, 24, 2, pants_s)
        elif frame == "walk2":
            d.hline(6, 19, 3, pants)
            d.hline(9, 19, 2, pants)
            d.hline(5, 20, 3, pants)
            d.hline(10, 20, 2, pants)
            d.hline(5, 21, 2, pants_s)
            d.hline(10, 21, 2, pants_s)
            d.hline(5, 22, 2, pants_s)
            d.hline(10, 22, 2, pants_s)
            d.hline(5, 23, 2, pants_s)
            d.hline(10, 23, 2, pants_s)
            d.hline(5, 24, 2, pants_s)
            d.hline(10, 24, 2, pants_s)
        else:
            # Standing (read)
            d.hline(7, 19, 3, pants)
            d.hline(7, 20, 3, pants)
            d.hline(7, 21, 3, pants)
            d.hline(7, 22, 3, pants_s)
            d.hline(7, 23, 3, pants_s)
            d.hline(7, 24, 3, pants_s)

    # Shoes
    if frame == "walk1":
        d.hline(10, 25, 3, shoes)
        d.hline(4, 25, 3, shoes)
        d.hline(10, 26, 3, shoes_s)
        d.hline(4, 26, 3, shoes_s)
        d.hline(10, 27, 3, shoes)
        d.hline(4, 27, 3, shoes)
    elif frame == "walk2":
        d.hline(4, 25, 3, shoes)
        d.hline(10, 25, 3, shoes)
        d.hline(4, 26, 3, shoes_s)
        d.hline(10, 26, 3, shoes_s)
        d.hline(4, 27, 3, shoes)
        d.hline(10, 27, 3, shoes)
    else:
        d.hline(6, 25, 4, shoes)
        d.hline(6, 26, 4, shoes_s)
        d.hline(6, 27, 4, shoes)

    d.hline(4, 29, 9, SHADOW_GROUND)
    d.hline(5, 30, 7, SHADOW_GROUND)


FRAMES = ["walk0", "walk1", "walk2", "type0", "type1", "read0", "read1"]
DIRECTIONS = ["down", "up", "right"]


def generate_spritesheet(char_id):
    pal = PALETTES[char_id]
    hair_func = HAIR_FUNCS[char_id]
    img = Image.new("RGBA", (SHEET_W, SHEET_H), T)

    for row_idx, direction in enumerate(DIRECTIONS):
        for col_idx, frame in enumerate(FRAMES):
            ox = col_idx * FRAME_W
            oy = row_idx * FRAME_H
            d = SpriteDrawer(img, ox, oy, pal)

            # 1. Draw hair
            hair_func(d, direction)

            # 2. Draw face
            if direction == "down":
                d.draw_face_down()
            elif direction == "up":
                d.draw_face_up()
            else:
                d.draw_face_right()

            # 3. Draw neck
            d.draw_neck(direction)

            # 4. Draw body
            if direction == "down":
                draw_body_down(d, char_id, frame)
            elif direction == "up":
                draw_body_up(d, char_id, frame)
            else:
                draw_body_right(d, char_id, frame)

    out_path = os.path.join(OUTPUT_DIR, f"{char_id}.png")
    img.save(out_path)
    print(f"Generated: {out_path} ({img.size[0]}x{img.size[1]})")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for char_id in PALETTES:
        generate_spritesheet(char_id)
    print(f"\nAll {len(PALETTES)} spritesheets generated successfully!")


if __name__ == "__main__":
    main()
