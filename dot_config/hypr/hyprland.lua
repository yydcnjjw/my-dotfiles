local hl = require("hyprland")

-- Monitors
hl.monitor({
  name = "",
  res = "preferred",
  pos = "auto",
  scale = 1
})

-- Environment variables
hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")

-- Config
hl.config({
  general = {
    gaps_in = 5,
    gaps_out = 10,
    border_size = 1,
    ["col.active_border"] = "rgba(33ccffee) rgba(00ff99ee) 45deg",
    ["col.inactive_border"] = "rgba(595959aa)",
    layout = "dwindle",
    allow_tearing = false,
  },
  decoration = {
    rounding = 10,
    blur = {
      enabled = true,
      size = 3,
      passes = 1,
      vibrancy = 0.1696,
    },
    drop_shadow = true,
    shadow_range = 4,
    shadow_render_power = 3,
    ["col.shadow"] = "rgba(1a1a1aee)",
  },
  animations = {
    enabled = true,
  },
  input = {
    kb_layout = "us",
    follow_mouse = 1,
    sensitivity = 0,
    touchpad = {
      natural_scroll = false,
    },
  },
  gestures = {
    workspace_swipe = false,
  },
  misc = {
    force_default_wallpaper = -1,
  },
})

-- Autostart
hl.on("hyprland.start", function()
  hl.dsp.exec_cmd("~/.config/hypr/autostart.sh")
end)

-- Variables
local mod = "SUPER"
local term = "alacritty"
local menu = "fuzzel"

-- Basics
hl.bind(mod .. ", Return", hl.dsp.exec_cmd(term))
hl.bind(mod .. "_SHIFT, Q", hl.dsp.window.close())
hl.bind(mod .. ", D", hl.dsp.exec_cmd(menu))
hl.bind(mod .. "_SHIFT, C", hl.dsp.exec_cmd("hyprctl reload"))
hl.bind(mod .. "_SHIFT, E", hl.dsp.exec_cmd("hyprctl dispatch exit"))
hl.bind(mod .. "_SHIFT, Escape", hl.dsp.exec_cmd("loginctl lock-session"))

-- Move focus
hl.bind(mod .. ", H", hl.dsp.focus({ direction = "left" }))
hl.bind(mod .. ", L", hl.dsp.focus({ direction = "right" }))
hl.bind(mod .. ", K", hl.dsp.focus({ direction = "up" }))
hl.bind(mod .. ", J", hl.dsp.focus({ direction = "down" }))

hl.bind(mod .. ", Left", hl.dsp.focus({ direction = "left" }))
hl.bind(mod .. ", Right", hl.dsp.focus({ direction = "right" }))
hl.bind(mod .. ", Up", hl.dsp.focus({ direction = "up" }))
hl.bind(mod .. ", Down", hl.dsp.focus({ direction = "down" }))

-- Move window
hl.bind(mod .. "_SHIFT, H", hl.dsp.window.move({ direction = "left" }))
hl.bind(mod .. "_SHIFT, L", hl.dsp.window.move({ direction = "right" }))
hl.bind(mod .. "_SHIFT, K", hl.dsp.window.move({ direction = "up" }))
hl.bind(mod .. "_SHIFT, J", hl.dsp.window.move({ direction = "down" }))

hl.bind(mod .. "_SHIFT, Left", hl.dsp.window.move({ direction = "left" }))
hl.bind(mod .. "_SHIFT, Right", hl.dsp.window.move({ direction = "right" }))
hl.bind(mod .. "_SHIFT, Up", hl.dsp.window.move({ direction = "up" }))
hl.bind(mod .. "_SHIFT, Down", hl.dsp.window.move({ direction = "down" }))

-- Workspaces
for i = 1, 10 do
  local key = i % 10
  hl.bind(mod .. ", " .. key, hl.dsp.focus({ workspace = i }))
  hl.bind(mod .. "_SHIFT, " .. key, hl.dsp.window.move({ workspace = i }))
end

-- Layout
hl.bind(mod .. ", F", hl.dsp.window.fullscreen())
hl.bind(mod .. "_SHIFT, Space", hl.dsp.window.float())
hl.bind(mod .. ", V", hl.dsp.layout("togglesplit"))

-- Scratchpad (Special workspace)
hl.bind(mod .. "_SHIFT, Minus", hl.dsp.window.move({ workspace = "special" }))
hl.bind(mod .. ", Grave", hl.dsp.workspace.toggle_special(""))

-- Media keys
hl.bind(", XF86AudioMute", hl.dsp.exec_cmd("pactl set-sink-mute @DEFAULT_SINK@ toggle"), { locked = true })
hl.bind(", XF86AudioLowerVolume", hl.dsp.exec_cmd("pactl set-sink-volume @DEFAULT_SINK@ -5%"), { locked = true })
hl.bind(", XF86AudioRaiseVolume", hl.dsp.exec_cmd("pactl set-sink-volume @DEFAULT_SINK@ +5%"), { locked = true })
hl.bind(", XF86AudioMicMute", hl.dsp.exec_cmd("pactl set-source-mute @DEFAULT_SOURCE@ toggle"), { locked = true })
hl.bind(", XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl set 5%-"), { locked = true })
hl.bind(", XF86MonBrightnessUp", hl.dsp.exec_cmd("brightnessctl set 5%+"), { locked = true })

-- Screenshot
hl.bind(mod .. "_SHIFT, Print", hl.dsp.exec_cmd("flameshot gui"))

-- Notification
hl.bind(mod .. "_SHIFT, N", hl.dsp.exec_cmd("makoctl dismiss"))
hl.bind(mod .. "_SHIFT, M", hl.dsp.exec_cmd("makoctl menu -- fuzzel -d"))
hl.bind(mod .. "_CONTROL, N", hl.dsp.exec_cmd("makoctl dismiss --all"))

-- Resize mode
hl.bind(mod .. ", R", hl.dsp.submap("resize"))
hl.submap("resize", {
  bindings = {
    { "", "H", hl.dsp.window.resize({ size = { -100, 0 } }), { repeating = true } },
    { "", "L", hl.dsp.window.resize({ size = { 100, 0 } }), { repeating = true } },
    { "", "K", hl.dsp.window.resize({ size = { 0, -100 } }), { repeating = true } },
    { "", "J", hl.dsp.window.resize({ size = { 0, 100 } }), { repeating = true } },
    { "", "Left", hl.dsp.window.resize({ size = { -100, 0 } }), { repeating = true } },
    { "", "Right", hl.dsp.window.resize({ size = { 100, 0 } }), { repeating = true } },
    { "", "Up", hl.dsp.window.resize({ size = { 0, -100 } }), { repeating = true } },
    { "", "Down", hl.dsp.window.resize({ size = { 0, 100 } }), { repeating = true } },
    { "", "Return", hl.dsp.submap("reset") },
    { "", "Escape", hl.dsp.submap("reset") },
  }
})

-- Mouse bindings
hl.bind(mod .. ", mouse:272", hl.dsp.window.drag())
hl.bind(mod .. ", mouse:273", hl.dsp.window.resize())

-- Window rules
hl.window_rule({
  windowid = "class:dropdown_terminal",
  workspace = "special",
  float = true,
  size = { "60%", "50%" },
  center = true,
})

hl.window_rule({
  windowid = "class:flameshot",
  float = true,
})

hl.window_rule({
  windowid = "class:org.fcitx.fcitx5-config-qt",
  float = true,
})

hl.window_rule({
  windowid = "class:org.pulseaudio.pavucontrol",
  float = true,
  size = { 800, 600 },
  center = true,
})

hl.window_rule({
  windowid = "class:blueman-manager",
  float = true,
  size = { 800, 600 },
  center = true,
})

hl.window_rule({
  windowid = "class:firefox",
  title = "Picture-in-Picture",
  float = true,
})

hl.window_rule({
  windowid = "class:google-chrome",
  title = "Save File",
  float = true,
})

-- RDP Passthrough Mode
hl.bind(mod .. "_SHIFT, P", hl.dsp.submap("passthrough"))
hl.submap("passthrough", {
  bindings = {
    { mod .. "_SHIFT, P", hl.dsp.submap("reset") },
  }
})
