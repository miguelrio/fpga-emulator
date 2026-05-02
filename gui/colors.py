"""Color palette for the FPGA simulator GUI."""

# Background
BG_DARK       = (15,  20,  30)
BG_PANEL      = (22,  30,  45)
BG_STAGE      = (30,  42,  60)
BG_STAGE_ACTIVE = (35, 55, 80)

# Stage border
BORDER_IDLE   = (60,  90, 130)
BORDER_ACTIVE = (80, 160, 220)
BORDER_PLUGIN = (120, 80, 200)   # purple for RTL plugin stages

# Packet token colors
TOKEN_IPV4_TCP = (50,  200, 100)  # green
TOKEN_IPV4_UDP = (50,  180,  80)
TOKEN_IPV6_TCP = (60,  140, 240)  # blue
TOKEN_IPV6_UDP = (40,  120, 210)
TOKEN_DROP     = (220,  60,  60)  # red flash

# Wire
WIRE_IDLE      = (40,  70, 110)
WIRE_ACTIVE    = (80, 160, 220)

# Glow (alpha-blended outer ring on active stage)
GLOW_COLORS = [
    (80, 160, 220, 40),
    (80, 160, 220, 25),
    (80, 160, 220, 12),
]
GLOW_PLUGIN = [
    (160, 100, 255, 40),
    (160, 100, 255, 25),
    (160, 100, 255, 12),
]

# Text
TEXT_PRIMARY   = (220, 230, 245)
TEXT_SECONDARY = (130, 155, 185)
TEXT_DIM       = (70,  90, 120)
TEXT_HIGHLIGHT = (100, 200, 255)
TEXT_WARN      = (255, 180,  60)
TEXT_ERROR     = (255,  80,  80)

# Panel / metrics
PANEL_BG       = (18,  25,  38)
PANEL_BORDER   = (40,  60,  90)
PANEL_HEADER   = (25,  40,  60)

# Bar chart
BAR_LUT        = (60,  160, 220)
BAR_FF         = (80,  200, 140)
BAR_BRAM       = (200, 120,  60)
BAR_BG         = (30,  45,  65)

# Timeline
TIMELINE_BG    = (18,  24,  36)
TIMELINE_FILL  = (50,  120, 200)
TIMELINE_CURSOR= (220, 180,  60)

# Buttons
BTN_NORMAL     = (40,  65,  95)
BTN_HOVER      = (55,  85, 125)
BTN_ACTIVE     = (70, 110, 160)
BTN_TEXT       = (200, 220, 240)

# Flash animation colors
FLASH_RELOAD   = (200, 140,  40)   # orange — plugin reloaded
FLASH_DROP     = (200,  50,  50)   # red — packet dropped
FLASH_HIT      = (50,  200, 100)   # green — FIB hit
