#!/bin/bash

# 从 stdin 读取 JSON 输入
input=$(cat)

# 使用 jq 解析通知类型、消息和详细信息
event=$(echo "$input" | jq -r '.notification_type // "Notification"')
message=$(echo "$input" | jq -r '.message // "No message provided"')
details=$(echo "$input" | jq -r '.details // empty')

# 如果是工具权限请求且包含 details，则提取工具名称并附加到消息中
if [ "$event" = "ToolPermission" ] && [ -n "$details" ]; then
    tool_name=$(echo "$details" | jq -r '.tool_name // empty')
    if [ -n "$tool_name" ] && [ "$tool_name" != "null" ]; then
        message="$message ($tool_name)"
    fi
fi

# 检测是否为 WSL 环境
is_wsl=false
if grep -qi microsoft /proc/version; then
    is_wsl=true
fi

if [ "$is_wsl" = true ]; then
    # --- WSL 环境 ---
    PWSH_PATH="/mnt/c/Users/yydcnjjw/AppData/Local/Microsoft/WindowsApps/Microsoft.PowerShell_8wekyb3d8bbwe/pwsh.exe"

    if [ -f "$PWSH_PATH" ]; then
        # 转义单引号以防止 PowerShell 命令注入或错误
        escaped_event=$(echo "$event" | sed "s/'/''/g")
        escaped_message=$(echo "$message" | sed "s/'/''/g")

        # 检查 BurntToast 模块是否存在
        if "$PWSH_PATH" -NoProfile -Command "Get-Module -ListAvailable BurntToast" > /dev/null 2>&1; then
            # 使用 BurntToast 发送通知
            "$PWSH_PATH" -NoProfile -Command "New-BurntToastNotification -Text 'Gemini - $escaped_event', '$escaped_message'"
            exit 0
        else
            # 如果 BurntToast 不存在，尝试使用 Windows 原生 PowerShell 脚本发送简单通知
            "$PWSH_PATH" -NoProfile -Command "
                [reflection.assembly]::loadwithpartialname('System.Windows.Forms');
                \$notification = New-Object System.Windows.Forms.NotifyIcon;
                \$notification.Icon = [System.Drawing.SystemIcons]::Information;
                \$notification.BalloonTipIcon = 'Info';
                \$notification.BalloonTipTitle = 'Gemini - $escaped_event';
                \$notification.BalloonTipText = '$escaped_message';
                \$notification.Visible = \$true;
                \$notification.ShowBalloonTip(5000);
            " > /dev/null 2>&1
            exit 0
        fi
    fi
fi

# --- 非 WSL 环境 或 WSL 下回退逻辑 ---
if command -v notify-send >/dev/null 2>&1; then
    notify-send "Gemini - $event" "$message"
else
    echo "Notification: Gemini - $event: $message"
fi
