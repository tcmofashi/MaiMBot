# MaiMBot Agent配置字段完整说明

## 概述

MaiMBot的Agent配置系统是一个完整的多层级、多租户隔离的配置管理体系，支持人格配置、行为配置、聊天配置等多个维度的灵活配置。本文档详细说明所有可用的配置字段。

## 1. Agent基础配置（Agent）

### 1.1 核心字段

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `agent_id` | string | ✅ | - | Agent的唯一标识符，通常格式为`tenant_id:agent_id` |
| `name` | string | ✅ | - | Agent的显示名称，用于界面展示 |
| `description` | string | ❌ | `""` | Agent的简要描述信息 |
| `tags` | string[] | ❌ | `[]` | 标签列表，用于分类和检索 |

### 1.2 配置覆盖字段

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `persona` | PersonalityConfig | ✅ | - | Agent专属的人格配置对象 |
| `bot_overrides` | object | ❌ | `{}` | Bot基础配置的覆盖项 |
| `config_overrides` | object | ❌ | `{}` | 整体配置系统的覆盖项 |

## 2. 人格配置（PersonalityConfig）

### 2.1 核心人格字段

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `personality` | string | ✅ | - | **人格核心描述**，定义AI的基本性格特征和行为准则 |

### 2.2 表达风格字段

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `reply_style` | string | ❌ | `""` | **回复风格**，如"轻松自然"、"正式礼貌"、"幽默风趣"等 |
| `interest` | string | ❌ | `""` | **兴趣领域**，影响对话内容的偏好和话题选择 |
| `plan_style` | string | ❌ | `""` | **群聊行为风格**，定义在群聊中的说话规则和行为模式 |
| `private_plan_style` | string | ❌ | `""` | **私聊行为风格**，定义在私聊中的说话规则和行为模式 |

### 2.3 多媒体风格字段

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `visual_style` | string | ❌ | `""` | **视觉风格**，生成图片时的提示词风格和美学偏好 |

### 2.4 状态系统字段

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `states` | string[] | ❌ | `[]` | **状态列表**，多种人格状态用于随机切换，增加对话多样性 |
| `state_probability` | float | ❌ | `0.0` | **状态切换概率**，0.0-1.0之间，控制人格状态随机切换的频率 |

**状态系统示例**：
```json
{
  "states": [
    "友善耐心的客服助手",
    "专业严谨的技术顾问",
    "轻松活泼的聊天伙伴"
  ],
  "state_probability": 0.15
}
```

## 3. Bot基础配置覆盖（BotConfig Overrides）

### 3.1 必需字段覆盖

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `platform` | string | ❌ | - | **运行平台**，如"qq"、"telegram"、"discord"等 |
| `qq_account` | string | ❌ | - | **QQ账号**，数字字符串格式 |
| `nickname` | string | ❌ | - | **机器人昵称**，在聊天中显示的名称 |

### 3.2 扩展字段覆盖

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `platforms` | string[] | ❌ | `[]` | **其他支持平台**列表 |
| `alias_names` | string[] | ❌ | `[]` | **别名列表**，用于识别机器人的多种称呼方式 |

**Bot配置示例**：
```json
{
  "bot_overrides": {
    "platform": "qq",
    "qq_account": "123456789",
    "nickname": "小助手",
    "platforms": ["qq", "telegram"],
    "alias_names": ["助手", "AI小助手", "小AI"]
  }
}
```

## 4. 整体配置覆盖（Config Overrides）

### 4.1 聊天配置覆盖（ChatConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `max_context_size` | int | ❌ | 18 | **上下文长度**，保留的历史消息数量 |
| `interest_rate_mode` | string | ❌ | `"fast"` | **兴趣计算模式**，"fast"快速或"accurate"精确 |
| `planner_size` | float | ❌ | 1.5 | **规划器大小**，控制AI执行能力，1.0-3.0 |
| `mentioned_bot_reply` | bool | ❌ | true | **提及回复**，被@时是否必须回复 |
| `auto_chat_value` | float | ❌ | 1.0 | **主动聊天频率**，数值越低，主动聊天概率越低 |
| `enable_auto_chat_value_rules` | bool | ❌ | true | **动态聊天频率**，是否启用基于时间的自动频率调整 |
| `at_bot_inevitable_reply` | float | ❌ | 1.0 | **@回复必然性**，1.0为100%回复，0.0为不额外增幅 |
| `planner_smooth` | float | ❌ | 3.0 | **规划器平滑**，减小规划器负荷，推荐2-5 |
| `talk_value` | float | ❌ | 1.0 | **思考频率**，AI主动思考和回复的频率 |
| `enable_talk_value_rules` | bool | ❌ | true | **动态思考频率**，是否启用基于时间的思考频率调整 |
| `talk_value_rules` | object[] | ❌ | `[]` | **思考频率规则**，基于时间的动态规则列表 |
| `auto_chat_value_rules` | object[] | ❌ | `[]` | **聊天频率规则**，基于时间的动态规则列表 |

**聊天配置示例**：
```json
{
  "config_overrides": {
    "chat": {
      "max_context_size": 20,
      "planner_size": 2.0,
      "auto_chat_value": 0.8,
      "planner_smooth": 4.0,
      "talk_value": 1.2
    }
  }
}
```

### 4.2 关系配置覆盖（RelationshipConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `enable_relationship` | bool | ❌ | true | **启用关系系统**，是否开启用户关系管理功能 |

### 4.3 表达配置覆盖（ExpressionConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `mode` | string | ❌ | `"classic"` | **表达模式**，"classic"经典或"exp_model"表达模型模式 |
| `learning_list` | array | ❌ | `[]` | **表达学习配置**列表，定义学习模式 |
| `expression_groups` | array | ❌ | `[]` | **表达学习互通组**，定义表达学习的分组规则 |

### 4.4 记忆配置覆盖（MemoryConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `max_memory_number` | int | ❌ | 100 | **记忆最大数量**，保留的长期记忆条数 |
| `memory_build_frequency` | int | ❌ | 1 | **记忆构建频率**，每N条消息构建一次记忆 |

### 4.5 情绪配置覆盖（MoodConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `enable_mood` | bool | ❌ | true | **启用情绪系统**，是否开启情绪状态管理 |
| `mood_update_threshold` | float | ❌ | 1.0 | **情绪更新阈值**，数值越高，情绪变化越缓慢 |
| `emotion_style` | string | ❌ | `"情绪较为稳定，但遭遇特定事件的时候起伏较大"` | **情感特征**，描述情绪变化的模式和特征 |

### 4.6 表情包配置覆盖（EmojiConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `emoji_chance` | float | ❌ | 0.6 | **表情包概率**，发送表情包的基础概率，0.0-1.0 |
| `max_reg_num` | int | ❌ | 200 | **最大注册数量**，表情包缓存的最大数量 |
| `do_replace` | bool | ❌ | true | **是否替换**，达到最大数量时是否替换旧表情包 |
| `check_interval` | int | ❌ | 120 | **检查间隔**，表情包检查间隔时间（分钟） |
| `steal_emoji` | bool | ❌ | true | **偷取表情包**，是否从聊天中学习新表情包 |
| `content_filtration` | bool | ❌ | false | **内容过滤**，是否开启表情包内容过滤 |
| `filtration_prompt` | string | ❌ | `"符合公序良俗"` | **过滤要求**，表情包内容过滤的标准描述 |

### 4.7 工具配置覆盖（ToolConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `enable_tool` | bool | ❌ | false | **启用工具**，是否在聊天中启用外部工具调用 |

### 4.8 语音配置覆盖（VoiceConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `enable_asr` | bool | ❌ | false | **语音识别**，是否启用语音转文字功能 |

### 4.9 插件配置覆盖（PluginConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `enable_plugins` | bool | ❌ | true | **启用插件**，是否启用插件系统 |
| `tenant_mode_disable_plugins` | bool | ❌ | true | **租户模式禁用**，多租户模式下是否禁用所有插件 |
| `allowed_plugins` | string[] | ❌ | `[]` | **允许插件**，白名单插件列表 |
| `blocked_plugins` | string[] | ❌ | `[]` | **禁止插件**，黑名单插件列表 |

### 4.10 关键词反应配置覆盖（KeywordReactionConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `keyword_rules` | object[] | ❌ | `[]` | **关键词规则**，基于关键词匹配的反应规则 |
| `regex_rules` | object[] | ❌ | `[]` | **正则规则**，基于正则表达式匹配的反应规则 |

### 4.11 人格配置覆盖（PersonalityConfig）

| 字段名 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `personality` | string | ❌ | - | **人格描述**，覆盖Agent的基础人格描述 |
| `reply_style` | string | ❌ | `""` | **回复风格**，覆盖基础的回复风格设置 |
| `interest` | string | ❌ | `""` | **兴趣领域**，覆盖基础的兴趣设置 |
| `plan_style` | string | ❌ | `""` | **群聊风格**，覆盖基础的群聊行为风格 |
| `private_plan_style` | string | ❌ | `""` | **私聊风格**，覆盖基础的私聊行为风格 |
| `visual_style` | string | ❌ | `""` | **视觉风格**，覆盖基础的图片生成风格 |
| `states` | string[] | ❌ | `[]` | **状态列表**，覆盖基础的人格状态列表 |
| `state_probability` | float | ❌ | 0.0 | **状态概率**，覆盖基础的状态切换概率 |

## 5. 完整配置示例

### 5.1 客服助手配置示例

```json
{
  "agent_id": "tenant_123:customer_service",
  "name": "客服小助手",
  "description": "专业的客户服务AI助手，提供高效友好的技术支持",
  "tags": ["客服", "技术支持", "专业"],
  "persona": {
    "personality": "我是专业的客服助手，具有耐心、细致、友善的特点。我致力于为用户提供准确、有用的技术支持和问题解答。",
    "reply_style": "专业、礼貌、耐心",
    "interest": "客户服务、技术支持、产品咨询、问题解决",
    "plan_style": "在群聊中保持专业形象，主动帮助需要支持的用户，耐心解答问题",
    "private_plan_style": "在私聊中更加个性化服务，详细了解用户问题并提供针对性解决方案",
    "visual_style": "温暖、专业的科技风格图像",
    "states": [
      "耐心细致的问题解答者",
      "高效专业的技术顾问",
      "友善热情的客服代表"
    ],
    "state_probability": 0.1
  },
  "bot_overrides": {
    "platform": "qq",
    "qq_account": "123456789",
    "nickname": "客服小助手",
    "alias_names": ["小助手", "客服", "技术支持"]
  },
  "config_overrides": {
    "chat": {
      "max_context_size": 25,
      "planner_size": 2.0,
      "auto_chat_value": 0.3,
      "planner_smooth": 4.0,
      "talk_value": 1.5
    },
    "emoji": {
      "emoji_chance": 0.3,
      "steal_emoji": false,
      "content_filtration": true
    },
    "memory": {
      "max_memory_number": 150,
      "memory_build_frequency": 1
    },
    "mood": {
      "enable_mood": true,
      "mood_update_threshold": 0.8,
      "emotion_style": "始终保持专业和友善的情绪状态"
    }
  }
}
```

### 5.2 娱乐聊天机器人配置示例

```json
{
  "agent_id": "tenant_456:entertainment_bot",
  "name": "聊天小能手",
  "description": "活泼有趣的聊天伙伴，擅长幽默对话和娱乐互动",
  "tags": ["娱乐", "聊天", "幽默", "活泼"],
  "persona": {
    "personality": "我是一个活泼开朗的聊天机器人，喜欢开玩笑、讲故事、分享有趣的内容。我善于调节气氛，让对话变得轻松愉快。",
    "reply_style": "轻松、幽默、有趣、活泼",
    "interest": "娱乐、游戏、笑话、故事、音乐、电影、动漫",
    "plan_style": "在群聊中积极参与话题，分享有趣内容，带动气氛",
    "private_plan_style": "在私聊中更加亲近，分享个人化的笑话和故事",
    "visual_style": "卡通、可爱、色彩鲜明的图像风格",
    "states": [
      "开心活泼的聊天伙伴",
      "幽默风趣的故事大王",
      "温柔体贴的倾听者"
    ],
    "state_probability": 0.25
  },
  "bot_overrides": {
    "platform": "discord",
    "nickname": "聊天小能手",
    "alias_names": ["小能手", "开心果", "幽默大师"]
  },
  "config_overrides": {
    "chat": {
      "max_context_size": 20,
      "auto_chat_value": 1.5,
      "talk_value": 1.8
    },
    "emoji": {
      "emoji_chance": 0.8,
      "steal_emoji": true,
      "content_filtration": false
    },
    "expression": {
      "mode": "exp_model",
      "learning_list": [["娱乐", "笑话", "表情包"]]
    }
  }
}
```

### 5.3 技术顾问配置示例

```json
{
  "agent_id": "tenant_789:tech_consultant",
  "name": "技术顾问",
  "description": "专业的技术顾问，提供深入的技术分析和解决方案",
  "tags": ["技术", "编程", "AI", "顾问"],
  "persona": {
    "personality": "我是资深的技术顾问，具有深厚的编程和技术背景。我善于分析复杂的技术问题，提供专业、准确的解决方案和建议。",
    "reply_style": "专业、严谨、逻辑清晰",
    "interest": "编程、算法、人工智能、软件工程、系统架构",
    "plan_style": "在群聊中提供专业技术分析，解答技术疑问，分享最佳实践",
    "private_plan_style": "在私聊中进行深入的技术讨论，提供定制化解决方案",
    "visual_style": "简洁、专业的技术图表和代码风格",
    "states": [
      "严谨的技术分析师",
      "创新的技术方案设计师",
      "耐心的技术导师"
    ],
    "state_probability": 0.05
  },
  "bot_overrides": {
    "platform": "slack",
    "nickname": "技术顾问",
    "alias_names": ["顾问", "技术专家", "导师"]
  },
  "config_overrides": {
    "chat": {
      "max_context_size": 30,
      "planner_size": 3.0,
      "auto_chat_value": 0.1,
      "talk_value": 0.8
    },
    "emoji": {
      "emoji_chance": 0.1
    },
    "tool": {
      "enable_tool": true
    },
    "memory": {
      "max_memory_number": 200,
      "memory_build_frequency": 1
    }
  }
}
```

## 6. 配置字段约束和验证

### 6.1 数值约束

| 字段类型 | 约束 | 说明 |
|----------|------|------|
| `float` | 0.0 ≤ value ≤ 1.0 | 概率类字段（如state_probability、emoji_chance） |
| `float` | value > 0.0 | 正数类字段（如planner_size、auto_chat_value） |
| `int` | value ≥ 1 | 计数类字段（如max_context_size、max_memory_number） |
| `string` | 1 ≤ length ≤ 10000 | 文本长度限制 |

### 6.2 枚举值约束

| 字段名 | 可选值 | 说明 |
|--------|--------|------|
| `interest_rate_mode` | `"fast"`, `"accurate"` | 兴趣计算模式 |
| `expression.mode` | `"classic"`, `"exp_model"` | 表达模式 |
| `platform` | `"qq"`, `"telegram"`, `"discord"`, `"slack"` | 支持的平台 |

### 6.3 JSON格式约束

- 所有配置字段都必须符合JSON格式规范
- 数组字段必须使用正确的JSON数组格式
- 嵌套对象必须有正确的键值对结构
- 字符串字段不能包含控制字符

## 7. 配置继承优先级

配置系统的继承优先级（从高到低）：

1. **平台配置** (`platform` 级别配置)
2. **智能体配置** (`agent` 级别配置)
3. **租户配置** (`tenant` 级别配置)
4. **全局配置** (`global` 级别配置)

同一级别下，`config_overrides` > `bot_overrides` > 基础配置。

## 8. 多租户隔离

配置系统支持T+A+C+P四维隔离：

- **T (Tenant)**: 租户隔离，不同租户的配置完全独立
- **A (Agent)**: 智能体隔离，同一租户内不同Agent的配置独立
- **C (Chat Stream)**: 聊天流隔离，同一Agent的不同聊天会话配置独立
- **P (Platform)**: 平台隔离，同一Agent在不同平台的配置独立

## 9. API使用说明

### 9.1 创建Agent时传递完整配置

```http
POST /api/v2/agents
Content-Type: application/json

{
  "tenant_id": "tenant_123",
  "name": "智能助手",
  "description": "专业的AI助手",
  "template_id": null,
  "config": {
    "persona": "...",
    "bot_overrides": {...},
    "config_overrides": {...},
    "tags": ["助手", "AI"]
  }
}
```

### 9.2 获取Agent时返回完整配置

```json
{
  "success": true,
  "data": {
    "agent_id": "agent_abc123",
    "tenant_id": "tenant_123",
    "name": "智能助手",
    "description": "专业的AI助手",
    "template_id": null,
    "config": {
      "persona": "...",
      "bot_overrides": {...},
      "config_overrides": {...},
      "tags": ["助手", "AI"]
    },
    "status": "active",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  }
}
```

## 10. 最佳实践建议

### 10.1 配置设计原则

1. **简洁明确**：人格描述应该清晰简洁，避免过于复杂或矛盾的表达
2. **一致性**：各个配置字段之间应该保持逻辑一致性
3. **适量配置**：不要过度配置，保持必要的灵活性即可
4. **测试验证**：配置后应该充分测试，确保符合预期行为

### 10.2 性能优化建议

1. **合理设置上下文长度**：根据对话复杂度调整`max_context_size`
2. **平衡主动聊天频率**：适当调整`auto_chat_value`和`talk_value`
3. **控制记忆数量**：合理设置`max_memory_number`避免内存过大
4. **选择合适模式**：根据需要选择`interest_rate_mode`（fast/accurate）

### 10.3 安全考虑

1. **内容过滤**：建议开启表情包和内容的过滤功能
2. **权限控制**：在多租户环境中合理配置插件权限
3. **敏感信息**：避免在配置中存储敏感的账号信息
4. **定期检查**：定期检查和更新配置，确保符合最新需求

---

**文档版本**: 1.0.0
**最后更新**: 2025-12-02
**适用版本**: MaiMBot v2.0+

如有疑问或需要技术支持，请参考项目文档或联系开发团队。