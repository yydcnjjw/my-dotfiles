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

summary="Gemini - $event"

send_notification() {
    if [ -n "${REMOTE_NOTIFY_HOST:-}" ] && command -v remote-notify >/dev/null 2>&1; then
        remote-notify -a Gemini "$summary" "$message" && return 0
    fi

    if command -v local-notify >/dev/null 2>&1; then
        local-notify -a Gemini "$summary" "$message" && return 0
    fi

    printf 'Notification: %s: %s\n' "$summary" "$message"
    return 0
}

send_notification
