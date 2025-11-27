# MaiMBot 数据库结构分析报告
**创建时间**: 2025年11月27日 23:26:28  
**数据库文件**: MaiBot.db  
**分析时间**: 2025-11-27T23:26:28.964570  
**AI生成标识**: Cline  
**文档类型**: 数据库结构分析报告

## 概述
本报告详细分析了 MaiMBot 项目中的数据库结构，共发现 26 个数据表。

## 数据库表列表
- `agents`
- `chat_streams`
- `llm_usage`
- `emoji`
- `messages`
- `images`
- `image_descriptions`
- `online_time`
- `person_info`
- `group_info`
- `expression`
- `graph_nodes`
- `graph_edges`
- `action_records`
- `memory_chest`
- `memory_conflicts`
- `jargon`
- `tenant_users`
- `agent_templates`
- `user_sessions`
- `isolatedconfigbase`
- `tenant_configs`
- `agent_configs`
- `platform_configs`
- `configtemplate`
- `confighistory`

## 详细表结构分析
### 表: `agents`

#### 表定义
```sql
CREATE TABLE "agents" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "name" TEXT NOT NULL, "description" TEXT, "tags" TEXT, "persona" TEXT NOT NULL, "bot_overrides" TEXT, "config_overrides" TEXT, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `name` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  |  | `NULL` |
| `tags` | `TEXT` |  |  | `NULL` |
| `persona` | `TEXT` |  | ✅ | `NULL` |
| `bot_overrides` | `TEXT` |  |  | `NULL` |
| `config_overrides` | `TEXT` |  |  | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `updated_at` | `DATETIME` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 索引
- `agentrecord_agent_id` (普通索引): `agent_id`
- `agentrecord_tenant_id` (普通索引): `tenant_id`

---

### 表: `chat_streams`

#### 表定义
```sql
CREATE TABLE "chat_streams" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT NOT NULL, "chat_stream_id" TEXT, "create_time" REAL NOT NULL, "group_platform" TEXT, "group_id" TEXT, "group_name" TEXT, "last_active_time" REAL NOT NULL, "user_platform" TEXT NOT NULL, "user_id" TEXT NOT NULL, "user_nickname" TEXT NOT NULL, "user_cardname" TEXT, "stream_id" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  | ✅ | `NULL` |
| `chat_stream_id` | `TEXT` |  |  | `NULL` |
| `create_time` | `REAL` |  | ✅ | `NULL` |
| `group_platform` | `TEXT` |  |  | `NULL` |
| `group_id` | `TEXT` |  |  | `NULL` |
| `group_name` | `TEXT` |  |  | `NULL` |
| `last_active_time` | `REAL` |  | ✅ | `NULL` |
| `user_platform` | `TEXT` |  | ✅ | `NULL` |
| `user_id` | `TEXT` |  | ✅ | `NULL` |
| `user_nickname` | `TEXT` |  | ✅ | `NULL` |
| `user_cardname` | `TEXT` |  |  | `NULL` |
| `stream_id` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `chatstreams_stream_id`: `stream_id`
- `chatstreams_chat_stream_id`: `chat_stream_id`

#### 索引
- `chatstreams_stream_id` (唯一索引): `stream_id`
- `chatstreams_chat_stream_id` (唯一索引): `chat_stream_id`
- `chatstreams_platform` (普通索引): `platform`
- `chatstreams_agent_id` (普通索引): `agent_id`
- `chatstreams_tenant_id` (普通索引): `tenant_id`

---

### 表: `llm_usage`

#### 表定义
```sql
CREATE TABLE "llm_usage" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT NOT NULL, "model_name" TEXT NOT NULL, "model_assign_name" TEXT, "model_api_provider" TEXT, "user_id" TEXT NOT NULL, "request_type" TEXT NOT NULL, "endpoint" TEXT NOT NULL, "prompt_tokens" INTEGER NOT NULL, "completion_tokens" INTEGER NOT NULL, "total_tokens" INTEGER NOT NULL, "cost" REAL NOT NULL, "time_cost" REAL, "status" TEXT NOT NULL, "timestamp" DATETIME NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  | ✅ | `NULL` |
| `model_name` | `TEXT` |  | ✅ | `NULL` |
| `model_assign_name` | `TEXT` |  |  | `NULL` |
| `model_api_provider` | `TEXT` |  |  | `NULL` |
| `user_id` | `TEXT` |  | ✅ | `NULL` |
| `request_type` | `TEXT` |  | ✅ | `NULL` |
| `endpoint` | `TEXT` |  | ✅ | `NULL` |
| `prompt_tokens` | `INTEGER` |  | ✅ | `NULL` |
| `completion_tokens` | `INTEGER` |  | ✅ | `NULL` |
| `total_tokens` | `INTEGER` |  | ✅ | `NULL` |
| `cost` | `REAL` |  | ✅ | `NULL` |
| `time_cost` | `REAL` |  |  | `NULL` |
| `status` | `TEXT` |  | ✅ | `NULL` |
| `timestamp` | `DATETIME` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 索引
- `llmusage_timestamp` (普通索引): `timestamp`
- `llmusage_request_type` (普通索引): `request_type`
- `llmusage_user_id` (普通索引): `user_id`
- `llmusage_model_name` (普通索引): `model_name`
- `llmusage_platform` (普通索引): `platform`
- `llmusage_agent_id` (普通索引): `agent_id`
- `llmusage_tenant_id` (普通索引): `tenant_id`

---

### 表: `emoji`

#### 表定义
```sql
CREATE TABLE "emoji" ("id" INTEGER NOT NULL PRIMARY KEY, "full_path" TEXT NOT NULL, "format" TEXT NOT NULL, "emoji_hash" TEXT NOT NULL, "description" TEXT NOT NULL, "query_count" INTEGER NOT NULL, "is_registered" INTEGER NOT NULL, "is_banned" INTEGER NOT NULL, "emotion" TEXT, "record_time" REAL NOT NULL, "register_time" REAL, "usage_count" INTEGER NOT NULL, "last_used_time" REAL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `full_path` | `TEXT` |  | ✅ | `NULL` |
| `format` | `TEXT` |  | ✅ | `NULL` |
| `emoji_hash` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  | ✅ | `NULL` |
| `query_count` | `INTEGER` |  | ✅ | `NULL` |
| `is_registered` | `INTEGER` |  | ✅ | `NULL` |
| `is_banned` | `INTEGER` |  | ✅ | `NULL` |
| `emotion` | `TEXT` |  |  | `NULL` |
| `record_time` | `REAL` |  | ✅ | `NULL` |
| `register_time` | `REAL` |  |  | `NULL` |
| `usage_count` | `INTEGER` |  | ✅ | `NULL` |
| `last_used_time` | `REAL` |  |  | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `emoji_full_path`: `full_path`

#### 索引
- `emoji_emoji_hash` (普通索引): `emoji_hash`
- `emoji_full_path` (唯一索引): `full_path`

---

### 表: `messages`

#### 表定义
```sql
CREATE TABLE "messages" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT NOT NULL, "chat_stream_id" TEXT NOT NULL, "message_id" TEXT NOT NULL, "time" REAL NOT NULL, "chat_id" TEXT, "reply_to" TEXT, "interest_value" REAL, "key_words" TEXT, "key_words_lite" TEXT, "is_mentioned" INTEGER, "is_at" INTEGER, "reply_probability_boost" REAL, "chat_info_stream_id" TEXT NOT NULL, "chat_info_platform" TEXT NOT NULL, "chat_info_user_platform" TEXT NOT NULL, "chat_info_user_id" TEXT NOT NULL, "chat_info_user_nickname" TEXT NOT NULL, "chat_info_user_cardname" TEXT, "chat_info_group_platform" TEXT, "chat_info_group_id" TEXT, "chat_info_group_name" TEXT, "chat_info_create_time" REAL NOT NULL, "chat_info_last_active_time" REAL NOT NULL, "user_platform" TEXT, "user_id" TEXT, "user_nickname" TEXT, "user_cardname" TEXT, "sender_user_platform" TEXT, "sender_user_id" TEXT, "sender_user_nickname" TEXT, "sender_user_cardname" TEXT, "sender_group_platform" TEXT, "sender_group_id" TEXT, "sender_group_name" TEXT, "receiver_user_platform" TEXT, "receiver_user_id" TEXT, "receiver_user_nickname" TEXT, "receiver_user_cardname" TEXT, "receiver_group_platform" TEXT, "receiver_group_id" TEXT, "receiver_group_name" TEXT, "processed_plain_text" TEXT, "display_message" TEXT, "priority_mode" TEXT, "priority_info" TEXT, "additional_config" TEXT, "is_emoji" INTEGER NOT NULL, "is_picid" INTEGER NOT NULL, "is_command" INTEGER NOT NULL, "is_notify" INTEGER NOT NULL, "selected_expressions" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  | ✅ | `NULL` |
| `chat_stream_id` | `TEXT` |  | ✅ | `NULL` |
| `message_id` | `TEXT` |  | ✅ | `NULL` |
| `time` | `REAL` |  | ✅ | `NULL` |
| `chat_id` | `TEXT` |  |  | `NULL` |
| `reply_to` | `TEXT` |  |  | `NULL` |
| `interest_value` | `REAL` |  |  | `NULL` |
| `key_words` | `TEXT` |  |  | `NULL` |
| `key_words_lite` | `TEXT` |  |  | `NULL` |
| `is_mentioned` | `INTEGER` |  |  | `NULL` |
| `is_at` | `INTEGER` |  |  | `NULL` |
| `reply_probability_boost` | `REAL` |  |  | `NULL` |
| `chat_info_stream_id` | `TEXT` |  | ✅ | `NULL` |
| `chat_info_platform` | `TEXT` |  | ✅ | `NULL` |
| `chat_info_user_platform` | `TEXT` |  | ✅ | `NULL` |
| `chat_info_user_id` | `TEXT` |  | ✅ | `NULL` |
| `chat_info_user_nickname` | `TEXT` |  | ✅ | `NULL` |
| `chat_info_user_cardname` | `TEXT` |  |  | `NULL` |
| `chat_info_group_platform` | `TEXT` |  |  | `NULL` |
| `chat_info_group_id` | `TEXT` |  |  | `NULL` |
| `chat_info_group_name` | `TEXT` |  |  | `NULL` |
| `chat_info_create_time` | `REAL` |  | ✅ | `NULL` |
| `chat_info_last_active_time` | `REAL` |  | ✅ | `NULL` |
| `user_platform` | `TEXT` |  |  | `NULL` |
| `user_id` | `TEXT` |  |  | `NULL` |
| `user_nickname` | `TEXT` |  |  | `NULL` |
| `user_cardname` | `TEXT` |  |  | `NULL` |
| `sender_user_platform` | `TEXT` |  |  | `NULL` |
| `sender_user_id` | `TEXT` |  |  | `NULL` |
| `sender_user_nickname` | `TEXT` |  |  | `NULL` |
| `sender_user_cardname` | `TEXT` |  |  | `NULL` |
| `sender_group_platform` | `TEXT` |  |  | `NULL` |
| `sender_group_id` | `TEXT` |  |  | `NULL` |
| `sender_group_name` | `TEXT` |  |  | `NULL` |
| `receiver_user_platform` | `TEXT` |  |  | `NULL` |
| `receiver_user_id` | `TEXT` |  |  | `NULL` |
| `receiver_user_nickname` | `TEXT` |  |  | `NULL` |
| `receiver_user_cardname` | `TEXT` |  |  | `NULL` |
| `receiver_group_platform` | `TEXT` |  |  | `NULL` |
| `receiver_group_id` | `TEXT` |  |  | `NULL` |
| `receiver_group_name` | `TEXT` |  |  | `NULL` |
| `processed_plain_text` | `TEXT` |  |  | `NULL` |
| `display_message` | `TEXT` |  |  | `NULL` |
| `priority_mode` | `TEXT` |  |  | `NULL` |
| `priority_info` | `TEXT` |  |  | `NULL` |
| `additional_config` | `TEXT` |  |  | `NULL` |
| `is_emoji` | `INTEGER` |  | ✅ | `NULL` |
| `is_picid` | `INTEGER` |  | ✅ | `NULL` |
| `is_command` | `INTEGER` |  | ✅ | `NULL` |
| `is_notify` | `INTEGER` |  | ✅ | `NULL` |
| `selected_expressions` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 索引
- `messages_chat_id` (普通索引): `chat_id`
- `messages_message_id` (普通索引): `message_id`
- `messages_chat_stream_id` (普通索引): `chat_stream_id`
- `messages_platform` (普通索引): `platform`
- `messages_agent_id` (普通索引): `agent_id`
- `messages_tenant_id` (普通索引): `tenant_id`

---

### 表: `images`

#### 表定义
```sql
CREATE TABLE "images" ("id" INTEGER NOT NULL PRIMARY KEY, "image_id" TEXT NOT NULL, "emoji_hash" TEXT NOT NULL, "description" TEXT, "path" TEXT NOT NULL, "count" INTEGER NOT NULL, "timestamp" REAL NOT NULL, "type" TEXT NOT NULL, "vlm_processed" INTEGER NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `image_id` | `TEXT` |  | ✅ | `NULL` |
| `emoji_hash` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  |  | `NULL` |
| `path` | `TEXT` |  | ✅ | `NULL` |
| `count` | `INTEGER` |  | ✅ | `NULL` |
| `timestamp` | `REAL` |  | ✅ | `NULL` |
| `type` | `TEXT` |  | ✅ | `NULL` |
| `vlm_processed` | `INTEGER` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `images_path`: `path`

#### 索引
- `images_path` (唯一索引): `path`
- `images_emoji_hash` (普通索引): `emoji_hash`

---

### 表: `image_descriptions`

#### 表定义
```sql
CREATE TABLE "image_descriptions" ("id" INTEGER NOT NULL PRIMARY KEY, "type" TEXT NOT NULL, "image_description_hash" TEXT NOT NULL, "description" TEXT NOT NULL, "timestamp" REAL NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `type` | `TEXT` |  | ✅ | `NULL` |
| `image_description_hash` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  | ✅ | `NULL` |
| `timestamp` | `REAL` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 索引
- `imagedescriptions_image_description_hash` (普通索引): `image_description_hash`

---

### 表: `online_time`

#### 表定义
```sql
CREATE TABLE "online_time" ("id" INTEGER NOT NULL PRIMARY KEY, "timestamp" TEXT NOT NULL, "duration" INTEGER NOT NULL, "start_timestamp" DATETIME NOT NULL, "end_timestamp" DATETIME NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `timestamp` | `TEXT` |  | ✅ | `NULL` |
| `duration` | `INTEGER` |  | ✅ | `NULL` |
| `start_timestamp` | `DATETIME` |  | ✅ | `NULL` |
| `end_timestamp` | `DATETIME` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 索引
- `onlinetime_end_timestamp` (普通索引): `end_timestamp`

---

### 表: `person_info`

#### 表定义
```sql
CREATE TABLE "person_info" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "is_known" INTEGER NOT NULL, "person_id" TEXT NOT NULL, "person_name" TEXT, "name_reason" TEXT, "platform" TEXT NOT NULL, "user_id" TEXT NOT NULL, "nickname" TEXT, "memory_points" TEXT, "know_times" REAL, "know_since" REAL, "last_know" REAL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `is_known` | `INTEGER` |  | ✅ | `NULL` |
| `person_id` | `TEXT` |  | ✅ | `NULL` |
| `person_name` | `TEXT` |  |  | `NULL` |
| `name_reason` | `TEXT` |  |  | `NULL` |
| `platform` | `TEXT` |  | ✅ | `NULL` |
| `user_id` | `TEXT` |  | ✅ | `NULL` |
| `nickname` | `TEXT` |  |  | `NULL` |
| `memory_points` | `TEXT` |  |  | `NULL` |
| `know_times` | `REAL` |  |  | `NULL` |
| `know_since` | `REAL` |  |  | `NULL` |
| `last_know` | `REAL` |  |  | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `personinfo_person_id`: `person_id`

#### 索引
- `personinfo_user_id` (普通索引): `user_id`
- `personinfo_person_id` (唯一索引): `person_id`
- `personinfo_tenant_id` (普通索引): `tenant_id`

---

### 表: `group_info`

#### 表定义
```sql
CREATE TABLE "group_info" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "group_id" TEXT NOT NULL, "group_name" TEXT, "platform" TEXT NOT NULL, "group_impression" TEXT, "member_list" TEXT, "topic" TEXT, "create_time" REAL, "last_active" REAL, "member_count" INTEGER)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `group_id` | `TEXT` |  | ✅ | `NULL` |
| `group_name` | `TEXT` |  |  | `NULL` |
| `platform` | `TEXT` |  | ✅ | `NULL` |
| `group_impression` | `TEXT` |  |  | `NULL` |
| `member_list` | `TEXT` |  |  | `NULL` |
| `topic` | `TEXT` |  |  | `NULL` |
| `create_time` | `REAL` |  |  | `NULL` |
| `last_active` | `REAL` |  |  | `NULL` |
| `member_count` | `INTEGER` |  |  | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `groupinfo_group_id`: `group_id`

#### 索引
- `groupinfo_group_id` (唯一索引): `group_id`
- `groupinfo_tenant_id` (普通索引): `tenant_id`

---

### 表: `expression`

#### 表定义
```sql
CREATE TABLE "expression" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "chat_stream_id" TEXT NOT NULL, "situation" TEXT NOT NULL, "style" TEXT NOT NULL, "context" TEXT, "up_content" TEXT, "last_active_time" REAL NOT NULL, "chat_id" TEXT, "create_date" REAL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `chat_stream_id` | `TEXT` |  | ✅ | `NULL` |
| `situation` | `TEXT` |  | ✅ | `NULL` |
| `style` | `TEXT` |  | ✅ | `NULL` |
| `context` | `TEXT` |  |  | `NULL` |
| `up_content` | `TEXT` |  |  | `NULL` |
| `last_active_time` | `REAL` |  | ✅ | `NULL` |
| `chat_id` | `TEXT` |  |  | `NULL` |
| `create_date` | `REAL` |  |  | `NULL` |

#### 主键
- `id`

#### 索引
- `expression_chat_id` (普通索引): `chat_id`
- `expression_chat_stream_id` (普通索引): `chat_stream_id`
- `expression_agent_id` (普通索引): `agent_id`
- `expression_tenant_id` (普通索引): `tenant_id`

---

### 表: `graph_nodes`

#### 表定义
```sql
CREATE TABLE "graph_nodes" ("id" INTEGER NOT NULL PRIMARY KEY, "concept" TEXT NOT NULL, "memory_items" TEXT NOT NULL, "weight" REAL NOT NULL, "hash" TEXT NOT NULL, "created_time" REAL NOT NULL, "last_modified" REAL NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `concept` | `TEXT` |  | ✅ | `NULL` |
| `memory_items` | `TEXT` |  | ✅ | `NULL` |
| `weight` | `REAL` |  | ✅ | `NULL` |
| `hash` | `TEXT` |  | ✅ | `NULL` |
| `created_time` | `REAL` |  | ✅ | `NULL` |
| `last_modified` | `REAL` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `graphnodes_concept`: `concept`

#### 索引
- `graphnodes_concept` (唯一索引): `concept`

---

### 表: `graph_edges`

#### 表定义
```sql
CREATE TABLE "graph_edges" ("id" INTEGER NOT NULL PRIMARY KEY, "source" TEXT NOT NULL, "target" TEXT NOT NULL, "strength" INTEGER NOT NULL, "hash" TEXT NOT NULL, "created_time" REAL NOT NULL, "last_modified" REAL NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `source` | `TEXT` |  | ✅ | `NULL` |
| `target` | `TEXT` |  | ✅ | `NULL` |
| `strength` | `INTEGER` |  | ✅ | `NULL` |
| `hash` | `TEXT` |  | ✅ | `NULL` |
| `created_time` | `REAL` |  | ✅ | `NULL` |
| `last_modified` | `REAL` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 索引
- `graphedges_target` (普通索引): `target`
- `graphedges_source` (普通索引): `source`

---

### 表: `action_records`

#### 表定义
```sql
CREATE TABLE "action_records" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "chat_stream_id" TEXT NOT NULL, "action_id" TEXT NOT NULL, "time" REAL NOT NULL, "action_reasoning" TEXT, "action_name" TEXT NOT NULL, "action_data" TEXT NOT NULL, "action_done" INTEGER NOT NULL, "action_build_into_prompt" INTEGER NOT NULL, "action_prompt_display" TEXT NOT NULL, "chat_id" TEXT, "chat_info_stream_id" TEXT, "chat_info_platform" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `chat_stream_id` | `TEXT` |  | ✅ | `NULL` |
| `action_id` | `TEXT` |  | ✅ | `NULL` |
| `time` | `REAL` |  | ✅ | `NULL` |
| `action_reasoning` | `TEXT` |  |  | `NULL` |
| `action_name` | `TEXT` |  | ✅ | `NULL` |
| `action_data` | `TEXT` |  | ✅ | `NULL` |
| `action_done` | `INTEGER` |  | ✅ | `NULL` |
| `action_build_into_prompt` | `INTEGER` |  | ✅ | `NULL` |
| `action_prompt_display` | `TEXT` |  | ✅ | `NULL` |
| `chat_id` | `TEXT` |  |  | `NULL` |
| `chat_info_stream_id` | `TEXT` |  |  | `NULL` |
| `chat_info_platform` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 索引
- `actionrecords_chat_id` (普通索引): `chat_id`
- `actionrecords_action_id` (普通索引): `action_id`
- `actionrecords_chat_stream_id` (普通索引): `chat_stream_id`
- `actionrecords_agent_id` (普通索引): `agent_id`
- `actionrecords_tenant_id` (普通索引): `tenant_id`

---

### 表: `memory_chest`

#### 表定义
```sql
CREATE TABLE "memory_chest" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT, "chat_stream_id" TEXT, "memory_level" TEXT NOT NULL, "memory_scope" TEXT NOT NULL, "title" TEXT NOT NULL, "content" TEXT NOT NULL, "chat_id" TEXT, "locked" INTEGER NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  |  | `NULL` |
| `chat_stream_id` | `TEXT` |  |  | `NULL` |
| `memory_level` | `TEXT` |  | ✅ | `NULL` |
| `memory_scope` | `TEXT` |  | ✅ | `NULL` |
| `title` | `TEXT` |  | ✅ | `NULL` |
| `content` | `TEXT` |  | ✅ | `NULL` |
| `chat_id` | `TEXT` |  |  | `NULL` |
| `locked` | `INTEGER` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 索引
- `memorychest_memory_scope` (普通索引): `memory_scope`
- `memorychest_memory_level` (普通索引): `memory_level`
- `memorychest_chat_stream_id` (普通索引): `chat_stream_id`
- `memorychest_platform` (普通索引): `platform`
- `memorychest_agent_id` (普通索引): `agent_id`
- `memorychest_tenant_id` (普通索引): `tenant_id`

---

### 表: `memory_conflicts`

#### 表定义
```sql
CREATE TABLE "memory_conflicts" ("id" INTEGER NOT NULL PRIMARY KEY, "conflict_content" TEXT NOT NULL, "answer" TEXT, "create_time" REAL NOT NULL, "update_time" REAL NOT NULL, "context" TEXT, "chat_id" TEXT, "raise_time" REAL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `conflict_content` | `TEXT` |  | ✅ | `NULL` |
| `answer` | `TEXT` |  |  | `NULL` |
| `create_time` | `REAL` |  | ✅ | `NULL` |
| `update_time` | `REAL` |  | ✅ | `NULL` |
| `context` | `TEXT` |  |  | `NULL` |
| `chat_id` | `TEXT` |  |  | `NULL` |
| `raise_time` | `REAL` |  |  | `NULL` |

#### 主键
- `id`

---

### 表: `jargon`

#### 表定义
```sql
CREATE TABLE "jargon" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "chat_stream_id" TEXT NOT NULL, "content" TEXT NOT NULL, "raw_content" TEXT, "type" TEXT, "translation" TEXT, "meaning" TEXT, "chat_id" TEXT, "is_global" INTEGER NOT NULL, "count" INTEGER NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `chat_stream_id` | `TEXT` |  | ✅ | `NULL` |
| `content` | `TEXT` |  | ✅ | `NULL` |
| `raw_content` | `TEXT` |  |  | `NULL` |
| `type` | `TEXT` |  |  | `NULL` |
| `translation` | `TEXT` |  |  | `NULL` |
| `meaning` | `TEXT` |  |  | `NULL` |
| `chat_id` | `TEXT` |  |  | `NULL` |
| `is_global` | `INTEGER` |  | ✅ | `NULL` |
| `count` | `INTEGER` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 索引
- `jargon_chat_id` (普通索引): `chat_id`
- `jargon_chat_stream_id` (普通索引): `chat_stream_id`
- `jargon_agent_id` (普通索引): `agent_id`
- `jargon_tenant_id` (普通索引): `tenant_id`

---

### 表: `tenant_users`

#### 表定义
```sql
CREATE TABLE "tenant_users" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "user_id" TEXT NOT NULL, "username" TEXT NOT NULL, "email" TEXT, "phone" TEXT, "password_hash" TEXT NOT NULL, "salt" TEXT NOT NULL, "api_key" TEXT NOT NULL, "status" TEXT NOT NULL, "tenant_type" TEXT NOT NULL, "tenant_name" TEXT NOT NULL, "tenant_config" TEXT, "permissions" TEXT NOT NULL, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL, "last_login_at" DATETIME, "login_count" INTEGER NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `user_id` | `TEXT` |  | ✅ | `NULL` |
| `username` | `TEXT` |  | ✅ | `NULL` |
| `email` | `TEXT` |  |  | `NULL` |
| `phone` | `TEXT` |  |  | `NULL` |
| `password_hash` | `TEXT` |  | ✅ | `NULL` |
| `salt` | `TEXT` |  | ✅ | `NULL` |
| `api_key` | `TEXT` |  | ✅ | `NULL` |
| `status` | `TEXT` |  | ✅ | `NULL` |
| `tenant_type` | `TEXT` |  | ✅ | `NULL` |
| `tenant_name` | `TEXT` |  | ✅ | `NULL` |
| `tenant_config` | `TEXT` |  |  | `NULL` |
| `permissions` | `TEXT` |  | ✅ | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `updated_at` | `DATETIME` |  | ✅ | `NULL` |
| `last_login_at` | `DATETIME` |  |  | `NULL` |
| `login_count` | `INTEGER` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `tenantusers_api_key`: `api_key`
- `tenantusers_user_id`: `user_id`
- `tenantusers_tenant_id`: `tenant_id`

#### 索引
- `tenantusers_api_key` (唯一索引): `api_key`
- `tenantusers_user_id` (唯一索引): `user_id`
- `tenantusers_tenant_id` (唯一索引): `tenant_id`

---

### 表: `agent_templates`

#### 表定义
```sql
CREATE TABLE "agent_templates" ("id" INTEGER NOT NULL PRIMARY KEY, "template_id" TEXT NOT NULL, "name" TEXT NOT NULL, "description" TEXT, "category" TEXT NOT NULL, "tags" TEXT, "is_active" INTEGER NOT NULL, "is_system" INTEGER NOT NULL, "usage_count" INTEGER NOT NULL, "persona" TEXT NOT NULL, "personality_traits" TEXT, "response_style" TEXT, "memory_config" TEXT, "plugin_config" TEXT NOT NULL, "config_schema" TEXT, "default_config" TEXT, "created_by" TEXT, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `template_id` | `TEXT` |  | ✅ | `NULL` |
| `name` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  |  | `NULL` |
| `category` | `TEXT` |  | ✅ | `NULL` |
| `tags` | `TEXT` |  |  | `NULL` |
| `is_active` | `INTEGER` |  | ✅ | `NULL` |
| `is_system` | `INTEGER` |  | ✅ | `NULL` |
| `usage_count` | `INTEGER` |  | ✅ | `NULL` |
| `persona` | `TEXT` |  | ✅ | `NULL` |
| `personality_traits` | `TEXT` |  |  | `NULL` |
| `response_style` | `TEXT` |  |  | `NULL` |
| `memory_config` | `TEXT` |  |  | `NULL` |
| `plugin_config` | `TEXT` |  | ✅ | `NULL` |
| `config_schema` | `TEXT` |  |  | `NULL` |
| `default_config` | `TEXT` |  |  | `NULL` |
| `created_by` | `TEXT` |  |  | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `updated_at` | `DATETIME` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `agenttemplates_template_id`: `template_id`

#### 索引
- `agenttemplates_template_id` (唯一索引): `template_id`

---

### 表: `user_sessions`

#### 表定义
```sql
CREATE TABLE "user_sessions" ("id" INTEGER NOT NULL PRIMARY KEY, "session_id" TEXT NOT NULL, "user_id" TEXT NOT NULL, "tenant_id" TEXT NOT NULL, "jwt_token" TEXT NOT NULL, "token_hash" TEXT NOT NULL, "refresh_token" TEXT, "expires_at" DATETIME NOT NULL, "created_at" DATETIME NOT NULL, "last_accessed_at" DATETIME NOT NULL, "ip_address" TEXT, "user_agent" TEXT, "is_active" INTEGER NOT NULL)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `session_id` | `TEXT` |  | ✅ | `NULL` |
| `user_id` | `TEXT` |  | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `jwt_token` | `TEXT` |  | ✅ | `NULL` |
| `token_hash` | `TEXT` |  | ✅ | `NULL` |
| `refresh_token` | `TEXT` |  |  | `NULL` |
| `expires_at` | `DATETIME` |  | ✅ | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `last_accessed_at` | `DATETIME` |  | ✅ | `NULL` |
| `ip_address` | `TEXT` |  |  | `NULL` |
| `user_agent` | `TEXT` |  |  | `NULL` |
| `is_active` | `INTEGER` |  | ✅ | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `usersessions_refresh_token`: `refresh_token`
- `usersessions_jwt_token`: `jwt_token`
- `usersessions_session_id`: `session_id`

#### 索引
- `usersessions_expires_at` (普通索引): `expires_at`
- `usersessions_refresh_token` (唯一索引): `refresh_token`
- `usersessions_token_hash` (普通索引): `token_hash`
- `usersessions_jwt_token` (唯一索引): `jwt_token`
- `usersessions_tenant_id` (普通索引): `tenant_id`
- `usersessions_user_id` (普通索引): `user_id`
- `usersessions_session_id` (唯一索引): `session_id`

---

### 表: `isolatedconfigbase`

#### 表定义
```sql
CREATE TABLE "isolatedconfigbase" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT, "config_level" TEXT NOT NULL, "config_category" TEXT NOT NULL, "config_key" TEXT NOT NULL, "config_value" TEXT NOT NULL, "config_type" TEXT NOT NULL, "description" TEXT, "is_active" INTEGER NOT NULL, "priority" INTEGER NOT NULL, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL, "created_by" TEXT, "updated_by" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  |  | `NULL` |
| `config_level` | `TEXT` |  | ✅ | `NULL` |
| `config_category` | `TEXT` |  | ✅ | `NULL` |
| `config_key` | `TEXT` |  | ✅ | `NULL` |
| `config_value` | `TEXT` |  | ✅ | `NULL` |
| `config_type` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  |  | `NULL` |
| `is_active` | `INTEGER` |  | ✅ | `NULL` |
| `priority` | `INTEGER` |  | ✅ | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `updated_at` | `DATETIME` |  | ✅ | `NULL` |
| `created_by` | `TEXT` |  |  | `NULL` |
| `updated_by` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 索引
- `isolatedconfigbase_tenant_id_agent_id_platform_config_level` (普通索引): `tenant_id`, `agent_id`, `platform`, `config_level`
- `isolatedconfigbase_config_key` (普通索引): `config_key`
- `isolatedconfigbase_config_category` (普通索引): `config_category`
- `isolatedconfigbase_config_level` (普通索引): `config_level`
- `isolatedconfigbase_platform` (普通索引): `platform`
- `isolatedconfigbase_agent_id` (普通索引): `agent_id`
- `isolatedconfigbase_tenant_id` (普通索引): `tenant_id`

---

### 表: `tenant_configs`

#### 表定义
```sql
CREATE TABLE "tenant_configs" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT, "config_level" TEXT NOT NULL, "config_category" TEXT NOT NULL, "config_key" TEXT NOT NULL, "config_value" TEXT NOT NULL, "config_type" TEXT NOT NULL, "description" TEXT, "is_active" INTEGER NOT NULL, "priority" INTEGER NOT NULL, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL, "created_by" TEXT, "updated_by" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  |  | `NULL` |
| `config_level` | `TEXT` |  | ✅ | `NULL` |
| `config_category` | `TEXT` |  | ✅ | `NULL` |
| `config_key` | `TEXT` |  | ✅ | `NULL` |
| `config_value` | `TEXT` |  | ✅ | `NULL` |
| `config_type` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  |  | `NULL` |
| `is_active` | `INTEGER` |  | ✅ | `NULL` |
| `priority` | `INTEGER` |  | ✅ | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `updated_at` | `DATETIME` |  | ✅ | `NULL` |
| `created_by` | `TEXT` |  |  | `NULL` |
| `updated_by` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `tenantconfig_tenant_id_config_category_config_key`: `tenant_id`, `config_category`, `config_key`

#### 索引
- `tenantconfig_tenant_id_config_category_config_key` (唯一索引): `tenant_id`, `config_category`, `config_key`
- `tenantconfig_config_key` (普通索引): `config_key`
- `tenantconfig_config_category` (普通索引): `config_category`
- `tenantconfig_config_level` (普通索引): `config_level`
- `tenantconfig_platform` (普通索引): `platform`
- `tenantconfig_agent_id` (普通索引): `agent_id`
- `tenantconfig_tenant_id` (普通索引): `tenant_id`

---

### 表: `agent_configs`

#### 表定义
```sql
CREATE TABLE "agent_configs" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT, "config_level" TEXT NOT NULL, "config_category" TEXT NOT NULL, "config_key" TEXT NOT NULL, "config_value" TEXT NOT NULL, "config_type" TEXT NOT NULL, "description" TEXT, "is_active" INTEGER NOT NULL, "priority" INTEGER NOT NULL, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL, "created_by" TEXT, "updated_by" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  |  | `NULL` |
| `config_level` | `TEXT` |  | ✅ | `NULL` |
| `config_category` | `TEXT` |  | ✅ | `NULL` |
| `config_key` | `TEXT` |  | ✅ | `NULL` |
| `config_value` | `TEXT` |  | ✅ | `NULL` |
| `config_type` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  |  | `NULL` |
| `is_active` | `INTEGER` |  | ✅ | `NULL` |
| `priority` | `INTEGER` |  | ✅ | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `updated_at` | `DATETIME` |  | ✅ | `NULL` |
| `created_by` | `TEXT` |  |  | `NULL` |
| `updated_by` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `agentconfig_tenant_id_agent_id_config_category_config_key`: `tenant_id`, `agent_id`, `config_category`, `config_key`

#### 索引
- `agentconfig_tenant_id_agent_id_config_category_config_key` (唯一索引): `tenant_id`, `agent_id`, `config_category`, `config_key`
- `agentconfig_config_key` (普通索引): `config_key`
- `agentconfig_config_category` (普通索引): `config_category`
- `agentconfig_config_level` (普通索引): `config_level`
- `agentconfig_platform` (普通索引): `platform`
- `agentconfig_agent_id` (普通索引): `agent_id`
- `agentconfig_tenant_id` (普通索引): `tenant_id`

---

### 表: `platform_configs`

#### 表定义
```sql
CREATE TABLE "platform_configs" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT, "config_level" TEXT NOT NULL, "config_category" TEXT NOT NULL, "config_key" TEXT NOT NULL, "config_value" TEXT NOT NULL, "config_type" TEXT NOT NULL, "description" TEXT, "is_active" INTEGER NOT NULL, "priority" INTEGER NOT NULL, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL, "created_by" TEXT, "updated_by" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  |  | `NULL` |
| `config_level` | `TEXT` |  | ✅ | `NULL` |
| `config_category` | `TEXT` |  | ✅ | `NULL` |
| `config_key` | `TEXT` |  | ✅ | `NULL` |
| `config_value` | `TEXT` |  | ✅ | `NULL` |
| `config_type` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  |  | `NULL` |
| `is_active` | `INTEGER` |  | ✅ | `NULL` |
| `priority` | `INTEGER` |  | ✅ | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `updated_at` | `DATETIME` |  | ✅ | `NULL` |
| `created_by` | `TEXT` |  |  | `NULL` |
| `updated_by` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `platformconfig_tenant_id_agent_id_platform_config_catego_7c77ce8`: `tenant_id`, `agent_id`, `platform`, `config_category`, `config_key`

#### 索引
- `platformconfig_tenant_id_agent_id_platform_config_catego_7c77ce8` (唯一索引): `tenant_id`, `agent_id`, `platform`, `config_category`, `config_key`
- `platformconfig_config_key` (普通索引): `config_key`
- `platformconfig_config_category` (普通索引): `config_category`
- `platformconfig_config_level` (普通索引): `config_level`
- `platformconfig_platform` (普通索引): `platform`
- `platformconfig_agent_id` (普通索引): `agent_id`
- `platformconfig_tenant_id` (普通索引): `tenant_id`

---

### 表: `configtemplate`

#### 表定义
```sql
CREATE TABLE "configtemplate" ("id" INTEGER NOT NULL PRIMARY KEY, "name" TEXT NOT NULL, "description" TEXT, "config_category" TEXT NOT NULL, "template_content" TEXT NOT NULL, "is_system" INTEGER NOT NULL, "is_active" INTEGER NOT NULL, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL, "created_by" TEXT, "updated_by" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `name` | `TEXT` |  | ✅ | `NULL` |
| `description` | `TEXT` |  |  | `NULL` |
| `config_category` | `TEXT` |  | ✅ | `NULL` |
| `template_content` | `TEXT` |  | ✅ | `NULL` |
| `is_system` | `INTEGER` |  | ✅ | `NULL` |
| `is_active` | `INTEGER` |  | ✅ | `NULL` |
| `created_at` | `DATETIME` |  | ✅ | `NULL` |
| `updated_at` | `DATETIME` |  | ✅ | `NULL` |
| `created_by` | `TEXT` |  |  | `NULL` |
| `updated_by` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 唯一约束
- `configtemplate_name`: `name`

#### 索引
- `configtemplate_config_category` (普通索引): `config_category`
- `configtemplate_name` (唯一索引): `name`

---

### 表: `confighistory`

#### 表定义
```sql
CREATE TABLE "confighistory" ("id" INTEGER NOT NULL PRIMARY KEY, "tenant_id" TEXT NOT NULL, "agent_id" TEXT NOT NULL, "platform" TEXT, "config_category" TEXT NOT NULL, "config_key" TEXT NOT NULL, "old_value" TEXT, "new_value" TEXT, "change_type" TEXT NOT NULL, "change_reason" TEXT, "operated_by" TEXT, "operated_at" DATETIME NOT NULL, "ip_address" TEXT, "user_agent" TEXT)
```

#### 列信息
| 列名 | 数据类型 | 是否主键 | 是否非空 | 默认值 |
|------|----------|----------|----------|--------|
| `id` | `INTEGER` | ✅ | ✅ | `NULL` |
| `tenant_id` | `TEXT` |  | ✅ | `NULL` |
| `agent_id` | `TEXT` |  | ✅ | `NULL` |
| `platform` | `TEXT` |  |  | `NULL` |
| `config_category` | `TEXT` |  | ✅ | `NULL` |
| `config_key` | `TEXT` |  | ✅ | `NULL` |
| `old_value` | `TEXT` |  |  | `NULL` |
| `new_value` | `TEXT` |  |  | `NULL` |
| `change_type` | `TEXT` |  | ✅ | `NULL` |
| `change_reason` | `TEXT` |  |  | `NULL` |
| `operated_by` | `TEXT` |  |  | `NULL` |
| `operated_at` | `DATETIME` |  | ✅ | `NULL` |
| `ip_address` | `TEXT` |  |  | `NULL` |
| `user_agent` | `TEXT` |  |  | `NULL` |

#### 主键
- `id`

#### 索引
- `confighistory_tenant_id_agent_id_platform` (普通索引): `tenant_id`, `agent_id`, `platform`
- `confighistory_change_type` (普通索引): `change_type`
- `confighistory_config_key` (普通索引): `config_key`
- `confighistory_config_category` (普通索引): `config_category`
- `confighistory_platform` (普通索引): `platform`
- `confighistory_agent_id` (普通索引): `agent_id`
- `confighistory_tenant_id` (普通索引): `tenant_id`

---
