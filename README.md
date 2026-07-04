# yelp-businesses-model

## 商业分析建模字段说明
运行类型检查脚本

```bash
python3 scripts/inspect_yelp_json_types.py --sample-lines 1000 --print-fields
```

字段类型报告输出：

```text
data/yelp_json_profile/
```

`business` 用于统计建模过程和指标；`user` 描述用户行为与影响力，适合刻画消费意愿、活跃度和评论权重。用于得到特征向量和维度变换过程。

## Business 字段

| 字段 | 类型 | 处理 |
|---|---|---|
| `city` | string | 类别变量，可用于 one-hot 编码 |
| `state` | string | 类别变量，可用于 one-hot 编码 |
| `postal_code` | string | 类别变量或地理分组 |
| `latitude` | float | 连续变量 |
| `longitude` | float | 连续变量 |
| `stars` | float | 视任务决定是否作为目标变量 |
| `review_count` | int | 连续变量，建议取 `log1p` |
| `categories` | string | 拆分为多标签变量 |
| `attributes` | object/null | 展开为结构化变量 |
| `hours` | object/null | 构造营业时间特征 |

## User 字段

| 字段 | 类型 | 处理 |
|---|---|---|
| `user_id` | string | 仅作连接键，不直接入模 |
| `review_count` | int | 连续变量，建议取 `log1p` |
| `yelping_since` | datetime string | 转为账号年龄 |
| `friends` | string | 转为 `friend_count` |
| `useful` | int | 连续变量，建议取 `log1p` |
| `funny` | int | 连续变量，建议取 `log1p` |
| `cool` | int | 连续变量，建议取 `log1p` |
| `fans` | int | 连续变量，建议取 `log1p` |
| `elite` | string | 转为 `is_elite`、`elite_year_count` |
| `average_stars` | float | 连续变量 |
| `compliment_hot` | int | 合并到赞美类指标 |
| `compliment_more` | int | 合并到赞美类指标 |
| `compliment_profile` | int | 合并到赞美类指标 |
| `compliment_cute` | int | 合并到赞美类指标 |
| `compliment_list` | int | 合并到赞美类指标 |
| `compliment_note` | int | 合并到赞美类指标 |
| `compliment_plain` | int | 合并到赞美类指标 |
| `compliment_cool` | int | 合并到赞美类指标 |
| `compliment_funny` | int | 合并到赞美类指标 |
| `compliment_writer` | int | 合并到赞美类指标 |
| `compliment_photos` | int | 合并到赞美类指标 |

## Review 字段

`review` 是连接用户和商家的核心交互表，负责建立 `user_id -> business_id` 的行为关系。

| 字段 | 类型 | 处理 |
|---|---|---|
| `review_id` | string | 仅作评论唯一标识，不直接入模 |
| `user_id` | string | 连接 `user` 表，作为用户行为指标映射键 |
| `business_id` | string | 连接 `business` 表，作为商家月度聚合键 |
| `stars` | float | 作为评论评分，可聚合为商家月度平均评分、评分波动 |
| `date` | datetime string | 转为月份、季度、星期、小时等时间特征 |
| `text` | string | 可提取文本长度、关键词、情感倾向；第一版可先用文本长度 |
| `useful` | int | 评论反馈数，建议取 `log1p` 或聚合为月度互动量 |
| `funny` | int | 评论反馈数，建议取 `log1p` 或聚合为月度互动量 |
| `cool` | int | 评论反馈数，建议取 `log1p` 或聚合为月度互动量 |


## 五大行为维度量化指标设计

围绕消费意愿、用户忠诚度、冲动消费、从众心理、分享表达欲

### 1. `monthly_review_rate`：月均评论密度

1. 统计需求，计算逻辑：以用户为统计对象，计算 `account_age_months = 数据集截至日期 - user.yelping_since`，再计算 `monthly_review_rate = user.review_count / account_age_months`。若账号年龄小于 1 个月，分母按 1 处理；该指标可进一步使用 `log1p` 缓解长尾分布。
2. 对应刻画的用户人性、消费行为特质：刻画消费意愿和平台活跃度。评论密度越高，说明用户越频繁地产生消费体验并愿意记录评价，可视为高频本地生活消费用户。
3. 商业预测价值的底层业务假设：高评论密度用户更可能持续消费、持续评价，也更可能对商家曝光和口碑扩散产生贡献，因此可用于预测用户活跃度、评论贡献价值和潜在消费频率。

### 2. `positive_rating_tendency`：正向评分倾向

1. 统计需求，计算逻辑：直接使用 `user.average_stars`，表示用户历史平均评分；也可按分位数划分为低评分倾向、中性评分倾向、高评分倾向三类。
2. 对应刻画的用户人性、消费行为特质：刻画消费满意倾向和评分宽严程度。平均评分高的用户通常更容易给出积极反馈，平均评分低的用户可能更挑剔或更容易表达不满。
3. 商业预测价值的底层业务假设：用户的历史评分习惯具有一定稳定性，会影响其未来评分和口碑反馈，因此该指标可作为评论星级预测、用户分层和商家口碑风险评估的控制变量。

### 3. `account_age_days`：账号年龄

1. 统计需求，计算逻辑：以用户注册时间 `user.yelping_since` 为起点，计算 `account_age_days = 当前基准日期 - user.yelping_since`。也可转换为 `account_age_months` 或 `account_age_years`。
2. 对应刻画的用户人性、消费行为特质：刻画用户忠诚度和平台沉淀程度。账号年龄越长，说明用户与平台关系越稳定，更可能形成长期消费记录和评价习惯。
3. 商业预测价值的底层业务假设：长期留存用户比新用户更具有行为稳定性，其历史行为对未来消费和评价更有预测力，可用于用户生命周期分析、留存价值评估和消费活跃度归一化。

### 4. `elite_year_count`：精英用户年数

1. 统计需求，计算逻辑：对 `user.elite` 字段按逗号拆分，统计有效年份数量，得到 `elite_year_count`；若为空则记为 0。同时可构造二值变量 `is_elite = elite_year_count > 0`。
2. 对应刻画的用户人性、消费行为特质：刻画用户忠诚度、社区参与度和意见领袖特质。Elite 年数越多，说明用户长期活跃且内容质量更可能被平台认可。
3. 商业预测价值的底层业务假设：精英用户的评论更可能被其他用户参考，对商家口碑传播和消费决策影响更强，因此可用于评论权重修正、意见领袖识别和口碑扩散建模。

### 5. `rating_volatility`：评分波动度

1. 统计需求，计算逻辑：基于 `review` 表按 `user_id` 聚合，计算用户历史评分标准差 `rating_volatility = std(review.stars)`。对于评论数过少的用户，可设为缺失、总体均值或加入平滑处理。
2. 对应刻画的用户人性、消费行为特质：刻画冲动消费和情绪化评价倾向。评分波动越大，说明用户对不同消费体验反应更分化，评价更受场景和即时情绪影响。
3. 商业预测价值的底层业务假设：评分波动大的用户未来评价不确定性更高，可能更容易产生极端好评或差评，因此可用于星级预测的不确定性控制、用户风险分层和极端评论预警。

### 6. `low_text_high_rating_ratio`：短文本高评分占比

1. 统计需求，计算逻辑：基于 `review` 表按 `user_id` 聚合，定义短文本高评分评论为 `len(review.text) < 50 且 review.stars >= 4`，计算 `low_text_high_rating_ratio = 短文本高评分评论数 / 用户评论总数`。
2. 对应刻画的用户人性、消费行为特质：刻画冲动消费和即时正反馈倾向。短文本高评分往往更像快速表达满意、打卡式评价或情绪驱动的即时反馈。
3. 商业预测价值的底层业务假设：短文本高评分占比高的用户更容易被即时体验、服务触点或促销刺激影响，因此可用于预测促销响应、即时评价倾向和高满意场景下的转化概率。

### 7. `popular_business_visit_ratio`：热门商家访问占比

1. 统计需求，计算逻辑：先用 `business.review_count` 定义热门商家，例如取评论数前 20% 的商家为热门商家；再基于 `review` 表按 `user_id` 聚合，计算 `popular_business_visit_ratio = 用户评论过的热门商家数 / 用户评论商家总数`。
2. 对应刻画的用户人性、消费行为特质：刻画从众心理和追热门倾向。该比例越高，说明用户越倾向选择已有高曝光、高评价样本量的商家。
3. 商业预测价值的底层业务假设：偏好热门商家的用户更容易受平台排名、口碑数量、推荐列表和大众选择影响，因此可用于推荐策略、爆款商家识别和热门商圈消费预测。

### 8. `friend_count`：好友数量

1. 统计需求，计算逻辑：对 `user.friends` 字段按逗号拆分，统计好友 ID 数量，得到 `friend_count`；若字段为空或为 `None`，记为 0。建模时建议使用 `log1p(friend_count)`。
2. 对应刻画的用户人性、消费行为特质：刻画从众心理、社交影响和口碑传播潜力。好友数量越多，用户越可能受到社交网络中评价、推荐和共同消费行为影响。
3. 商业预测价值的底层业务假设：社交关系更强的用户更可能参与口碑扩散，并影响或被影响于群体消费选择，因此可用于用户影响力评估、社交推荐和消费扩散预测。

### 9. `avg_review_text_length`：平均评论文本长度

1. 统计需求，计算逻辑：基于 `review` 表按 `user_id` 聚合，计算 `avg_review_text_length = mean(len(review.text))`。为缓解长尾，可使用 `log1p(avg_review_text_length)`。
2. 对应刻画的用户人性、消费行为特质：刻画分享表达欲和信息贡献深度。平均文本越长，说明用户越愿意详细描述消费体验、服务细节和主观感受。
3. 商业预测价值的底层业务假设：高表达欲用户提供的信息更丰富，对其他消费者决策更有参考价值，也更有利于提取服务、价格、环境等细粒度口碑信号，因此可用于评论质量评估和文本口碑分析。

### 10. `feedback_per_review`：单条评论平均反馈

1. 统计需求，计算逻辑：使用 `user.useful`、`user.funny`、`user.cool` 与 `user.review_count` 计算 `feedback_per_review = (useful + funny + cool) / review_count`。当 `review_count = 0` 时设为 0 或缺失，建模时可使用 `log1p` 或分位数缩尾。
2. 对应刻画的用户人性、消费行为特质：刻画分享表达欲、评论影响力和内容被认可程度。该指标越高，说明用户平均每条评论能获得更多互动反馈。
3. 商业预测价值的底层业务假设：被更多人认为有用、有趣或有吸引力的评论更可能影响其他消费者决策，因此该指标可用于评论权重分配、用户影响力建模和口碑传播效果预测。


## 统一建模目标

本题最终统一到一个预测问题：**预测商家未来月度热度**。这里不直接用真实客流量，因为数据集中没有线下订单或到店人数，所以用“下一月新增评论数量”作为代理标签。

可以这样理解：

```text
商家未来月度热度 = 该商家下一月新增 review 数量
```

数学上记为：

```text
Y_{b,t+1} = review_count_{b,t+1}
```

其中 `b` 表示某个商家，`t` 表示当前月份，`t+1` 表示下一月份。

这个定义和 Yelp JSON 数据是对齐的：`review` 表同时有 `user_id`、`business_id`、`date` 和 `stars`，它既能说明“哪个用户评价了哪个商家”，也能说明“评价发生在什么时候”。因此，`review` 是本方案里最核心的交互表。

## 数据口径

当前 Yelp JSON 数据主要包含 5 张表：

| 表 | 样本量 | 在本方案中的作用 |
|---|---:|---|
| `business` | 150346 | 提供商家基础属性，如城市、类别、经纬度、营业时间、属性配置 |
| `user` | 1987897 | 提供用户历史行为与影响力字段，用于构造人性指标 |
| `review` | 6990280 | 建立用户和商家的交互关系，也是月度热度标签来源 |
| `tip` | 908915 | 可作为轻量分享行为补充特征 |
| `checkin` | 131930 | 可作为商家层面的到店热度补充，但没有 `user_id`，不能连接到具体用户 |

`review` 表的时间范围为：

```text
2005-02-16 03:23:22 至 2022-01-19 19:48:45
```

因此执行时间切分时不能写 2023 年数据。由于 2022 年 1 月不是完整月份，第一版建模建议只把完整月份用到 2021 年 12 月。

## 样本粒度

这里最重要的一点是：**人性指标不是直接属于某个商家的，它们属于用户。**

所以我们不能写成：

```text
某个用户的人性特征 -> 某个商家的未来流量
```

更合理的口径是：

```text
用户人性特征
  + 用户对商家的当期评论行为
  -> 聚合为商家-月份层面的客群画像和口碑状态
  -> 预测商家下一月新增评论数量
```

最终训练数据的一行应该是：

```text
一行样本 = 某个商家 b 在某个月份 t 的状态
标签 = 该商家 b 在 t+1 月的新增评论数量
```

示例：

| business_id | month | 当月评论数 | 当月平均评分 | 当月评论用户平均好友数 | Elite 用户占比 | 下月新增评论数 |
|---|---|---:|---:|---:|---:|---:|
| B001 | 2021-05 | 32 | 4.20 | 73.5 | 0.25 | 41 |

这里的“当月评论用户平均好友数”和“Elite 用户占比”才是和商家 B001 绑定后的特征。它们描述的不是商家本身，而是这个商家当月吸引到的客群结构。

## 特征如何对齐到商家

本方案分三层构造特征。

### 1. 商家基础特征

这部分来自 `business` 表，属于商家相对稳定的属性：

| 特征 | 来源 | 处理方式 |
|---|---|---|
| 城市、州、邮编 | `city`, `state`, `postal_code` | 类别编码 |
| 经纬度 | `latitude`, `longitude` | 连续变量 |
| 商家类别 | `categories` | 拆成多标签变量 |
| 营业状态 | `hours` | 转成每周营业天数、周末是否营业 |
| 商家属性 | `attributes` | 展开价格区间、是否外卖、是否停车、是否 WiFi 等 |

### 2. 商家历史热度特征

这部分来自 `review`，按 `business_id + month` 聚合：

| 特征 | 计算逻辑 |
|---|---|
| `review_count_1m` | 商家当前月新增评论数 |
| `review_count_3m` | 商家过去 3 个月新增评论数 |
| `avg_stars_1m` | 商家当前月平均评分 |
| `avg_text_len_1m` | 商家当前月评论文本平均长度 |
| `feedback_count_1m` | 当前月评论的 `useful + funny + cool` 总和 |

这些特征代表商家当前的口碑状态和热度惯性。一般来说，一个商家当前月越热，下个月继续获得评论的概率也越高。

### 3. 商家当期客群画像特征

这部分是把前面设计的 10 个用户人性指标，通过 `review.user_id` 和 `review.business_id` 映射到商家，再按商家-月份聚合。

举例来说：

| 商家月度特征 | 计算逻辑 |
|---|---|
| `avg_monthly_review_rate` | 当月评论该商家的用户，其 `monthly_review_rate` 的平均值 |
| `avg_positive_rating_tendency` | 当月评论用户的 `average_stars` 平均值 |
| `avg_account_age_days` | 当月评论用户的账号年龄平均值 |
| `elite_user_ratio` | 当月评论用户中 `elite_year_count > 0` 的占比 |
| `avg_rating_volatility` | 当月评论用户评分波动度平均值 |
| `avg_low_text_high_rating_ratio` | 当月评论用户短文本高评分占比的平均值 |
| `avg_popular_business_visit_ratio` | 当月评论用户热门商家访问倾向平均值 |
| `avg_friend_count` | 当月评论用户好友数量平均值 |
| `avg_review_text_length` | 当月评论用户历史平均评论长度 |
| `avg_feedback_per_review` | 当月评论用户单条评论平均反馈 |

这样处理之后，原来的“用户人性指标”就变成了“商家当月吸引到的用户群体画像”。这一步是整个方案的关键。

## 用户-商家交互特征

除了用户画像，还可以从 `review` 表里提取用户和特定商家之间的历史交互特征。这里不使用照片比例，因为当前 JSON 的 `review` 表没有图片字段。

| 交互特征 | 计算逻辑 |
|---|---|
| `inter_avg_stars` | 某用户过去给该商家的历史平均评分 |
| `inter_review_freq` | 某用户过去评论该商家的次数 |
| `inter_recency_days` | 某用户最近一次评论该商家距当前月的天数 |
| `inter_feedback_count` | 该用户对该商家历史评论收到的 `useful + funny + cool` 总数 |
| `inter_text_len` | 该用户对该商家历史评论的平均文本长度 |

这些交互特征也需要先在用户-商家层面计算，再聚合到商家-月份层面，例如取平均值、中位数、最大值或时间衰减加权平均。

## 时间切分

为了避免数据泄露，预测 `t+1` 月热度时，所有特征只能使用 `t` 月及以前的信息。

本数据集中 review 的完整月份可以使用到 2021 年 12 月，所以第一版可以采用：

| 数据集 | 标签月份 | 特征使用范围 |
|---|---|---|
| 训练集 | 2005-03 至 2020-12 | 每个标签月之前的信息 |
| 验证集 | 2021-01 至 2021-06 | 每个标签月之前的信息 |
| 测试集 | 2021-07 至 2021-12 | 每个标签月之前的信息 |

注意：`user.review_count`、`user.useful`、`business.review_count`、`business.stars` 这类字段在原始表中可能是全量累计值。如果直接拿来预测历史某个月，会把未来信息带进去。更严谨的做法是从 `review` 表按时间重新累计，只保留预测月份之前已经发生的行为。

## 模型选择

第一版建议先用结构化模型，不急着上复杂神经网络。原因很简单：当前目标是商家月度新增评论数，本质上是一个计数型预测问题，商家-月份面板数据加树模型或计数回归就能形成可解释基线。

推荐模型顺序：

| 模型 | 用途 |
|---|---|
| 上月评论数基线 | 判断模型是否真的超过简单惯性 |
| Poisson 回归 | 适合新增评论数这种计数目标 |
| 负二项回归 | 适合过度离散的评论数数据 |
| Random Forest / XGBoost | 捕捉非线性和特征交互，作为主力基线 |

目标函数可以先用 MAE、RMSE、RMSLE。由于商家热度通常长尾明显，RMSLE 会比单纯 RMSE 更稳定。

## 执行步骤

第一版落地可以按下面顺序做：

1. 读取 `review`，生成商家-月份表，标签为下一月新增评论数。
2. 从 `business` 生成商家基础特征，并合并到商家-月份表。
3. 从 `user` 和 `review` 生成 10 个用户人性指标。
4. 通过 `review.user_id + review.business_id + review.date`，把用户指标聚合成商家-月份客群画像。
5. 从 `review` 生成商家历史热度特征和用户-商家交互特征。
6. 按时间切分训练集、验证集和测试集。
7. 训练 Poisson / 负二项 / XGBoost 等基线模型。
8. 输出测试集 MAE、RMSE、RMSLE，并分析重要特征。

建议拆成以下代码文件：

| 文件 | 作用 |
|---|---|
| `scripts/build_monthly_panel.py` | 构造商家-月份样本、下一月标签和主要特征 |
| `scripts/train_baseline.py` | 训练标准库 log-linear 基线，并和上月评论数基线对比 |
| `scripts/generate_dashboard.py` | 生成可视化结果页面 |
| `scripts/inspect_yelp_json_types.py` | 检查 Yelp JSON 字段类型和数据结构 |

## 方案总结

本方案不是把“某一个用户的人性特征”直接拿去预测“某一个商家的流量”。更准确地说，是先用用户历史行为构造五大人性指标，再通过 `review` 表把这些指标映射到具体商家，并在商家-月份粒度上聚合成客群画像。

最终模型预测的是：

```text
商家基础属性 + 商家历史热度 + 当期客群画像 + 用户-商家交互状态
-> 商家下一月新增评论数量
```

这样一来，人性指标和商家未来热度之间的关系就变得清楚了：它们不是直接因果关系，而是通过“商家吸引到什么样的用户”和“这些用户是否有传播、复访、表达和从众特征”间接影响未来热度。

## 当前训练结果

已按上述方案完成第一版训练，使用模型为标准库实现的 log-linear baseline，并与“上月评论数”朴素基线对比。

| 数据集 | 样本数 | 模型 MAE | 上月基线 MAE | 模型 RMSLE | 上月基线 RMSLE |
|---|---:|---:|---:|---:|---:|
| train | 3045832 | 0.9438 | 1.3335 | 0.4740 | 0.6740 |
| valid | 153952 | 0.9452 | 1.2959 | 0.4915 | 0.6709 |
| test | 159784 | 0.9164 | 1.3034 | 0.4888 | 0.6768 |

主要输出文件：

| 文件 | 说明 |
|---|---|
| `data/model/business_month_panel.csv` | 商家-月份训练面板，本地生成，文件较大不提交 GitHub |
| `models/monthly_popularity_log_linear.json` | 训练后的 log-linear 模型参数 |
| `reports/metrics.json` | 训练、验证、测试误差 |
| `reports/feature_importance.csv` | 特征重要性 |
| `reports/predictions_sample.csv` | 测试集预测样例 |
| `reports/dashboard.html` | 可视化结果页面 |

## GitHub 提交说明

本仓库提交关键代码、报告说明、小型模型结果和可视化页面；不提交原始 Yelp 压缩数据和大型中间面板。原因是原始数据和 `business_month_panel.csv` 文件过大，不适合直接放入 GitHub。

已提交/建议提交内容：

| 类型 | 路径 |
|---|---|
| 文档 | `README.md` |
| 数据检查脚本 | `scripts/inspect_yelp_json_types.py` |
| 面板构造脚本 | `scripts/build_monthly_panel.py` |
| 基线训练脚本 | `scripts/train_baseline.py` |
| 可视化脚本 | `scripts/generate_dashboard.py` |
| 小型数据概览 | `data/yelp_json_profile/*.csv`, `data/yelp_json_profile/schema_summary.json` |
| 面板摘要 | `data/model/panel_summary.json` |
| 模型与报告 | `models/*.json`, `reports/*` |

未提交内容：

| 类型 | 路径 | 原因 |
|---|---|---|
| 原始 Yelp 数据 | `data/yelp_json_raw/` | 文件约 4GB，超过 GitHub 常规提交范围 |
| 大型训练面板 | `data/model/business_month_panel.csv` | 文件约 799MB，可由脚本重新生成 |

复现实验流程：

```bash
python3 scripts/inspect_yelp_json_types.py --sample-lines 1000 --print-fields
python3 scripts/build_monthly_panel.py
python3 scripts/train_baseline.py --epochs 6 --lr 0.001
python3 scripts/generate_dashboard.py
```
