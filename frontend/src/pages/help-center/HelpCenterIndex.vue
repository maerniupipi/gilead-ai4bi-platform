<template>
  <div class="help-center-layout">
    <!-- 左侧导航 -->
    <aside class="help-sidebar">
      <nav class="sidebar-nav">
        <div
          v-for="section in navSections"
          :key="section.key"
          class="nav-group"
        >
          <div
            class="nav-item"
            :class="{ active: activeSection === section.key }"
            @click="activeSection = section.key"
          >
            <el-icon><component :is="section.icon" /></el-icon>
            <span>{{ section.label }}</span>
          </div>
        </div>
      </nav>
    </aside>

    <!-- 右侧内容 -->
    <main class="help-content">
      <div class="content-inner">
        <!-- 产品概述 -->
        <template v-if="activeSection === 'overview'">
          <div class="page-header">
            <h1>产品概述</h1>
            <p class="section-desc">AI4BI 是一款企业级智能数据分析平台，将大语言模型能力与结构化数据分析深度融合，让业务人员无需编写 SQL 即可通过自然语言完成复杂的数据查询、分析与可视化。</p>
          </div>

          <div class="info-card highlight-card">
            <h3>核心价值</h3>
            <div class="value-grid">
              <div class="value-item">
                <div class="value-num">90%</div>
                <div class="value-label">降低数据查询门槛</div>
                <p>业务人员直接用自然语言提问，无需依赖数据开发人员编写 SQL</p>
              </div>
              <div class="value-item">
                <div class="value-num">5x</div>
                <div class="value-label">提升分析效率</div>
                <p>从提问到可视化结果，秒级响应，替代传统报表开发周期</p>
              </div>
              <div class="value-item">
                <div class="value-num">100+</div>
                <div class="value-label">支撑业务场景</div>
                <p>覆盖销售分析、财务对账、运营监控、经营决策等核心场景</p>
              </div>
            </div>
          </div>

          <h2>系统架构</h2>
          <p class="h2-desc">平台由四大核心模块组成，各模块既独立运行又相互协同：</p>
          <div class="arch-list">
            <div class="arch-item" @click="activeSection = 'chatbi'">
              <div class="arch-badge chatbi">ChatBI</div>
              <div>
                <strong>智能数据分析引擎</strong>
                <p>数据源接入、知识库配置、自然语言问答、实验室，是平台的核心交互入口</p>
              </div>
            </div>
            <div class="arch-item" @click="activeSection = 'agent'">
              <div class="arch-badge agent">工作流</div>
              <div>
                <strong>AI 工作流自动化</strong>
                <p>可视化编排 AI 工作流，结合工具、知识库和插件构建复杂分析任务</p>
              </div>
            </div>
            <div class="arch-item" @click="activeSection = 'eval'">
              <div class="arch-badge eval">评测中心</div>
              <div>
                <strong>质量保障与调优</strong>
                <p>通过评测集和自动化评测任务持续优化模型效果和问答准确率</p>
              </div>
            </div>
            <div class="arch-item" @click="activeSection = 'management'">
              <div class="arch-badge mgmt">系统管理</div>
              <div>
                <strong>基础设施配置</strong>
                <p>模型服务、存储资源、用户权限、多租户空间的统一管理后台</p>
              </div>
            </div>
          </div>

          <h2>快速上手</h2>
          <p class="h2-desc">初次使用建议按照以下顺序完成基本配置，从数据接入到工作流搭建，五步即可跑通完整流程：</p>
          <div class="steps-list">
            <div class="step-row">
              <div class="step-num">1</div>
              <div>
                <strong>配置模型服务</strong>
                <p>进入「系统管理 → 语言模型」，添加大语言模型服务商。平台支持 OpenAI、Azure OpenAI、文心一言、通义千问、DeepSeek 等主流服务商。填写服务地址和 API 密钥后，点击「测试连接」确认连通性。建议同时配置向量模型（用于知识库检索）和多模态模型（如需图像分析能力）。</p>
              </div>
            </div>
            <div class="step-row">
              <div class="step-num">2</div>
              <div>
                <strong>接入数据源</strong>
                <p>进入「ChatBI → 数据中心」，点击「新增数据源」添加业务数据库连接。支持 MySQL、PostgreSQL 等关系型数据库，填写主机地址、端口、数据库名和认证信息即可完成接入。添加成功后系统会自动读取数据库的表结构信息，为后续的知识库配置做好准备。建议为不同业务线创建独立的数据源连接，便于后续权限隔离。</p>
              </div>
            </div>
            <div class="step-row">
              <div class="step-num">3</div>
              <div>
                <strong>构建知识库</strong>
                <p>进入「ChatBI → 知识引擎」选择已接入的数据源，勾选需要开放给问答系统的数据表，并为每个字段添加中文描述和业务含义说明。然后前往「ChatBI → 知识中心」进一步完善知识资产：添加业务术语词条（如"毛利率 = (收入-成本)/收入"）、配置 NER 实体识别规则、录入典型问答样例作为 few-shot 示例。知识库越完善，问答准确率越高。</p>
              </div>
            </div>
            <div class="step-row">
              <div class="step-num">4</div>
              <div>
                <strong>配置实验室</strong>
                <p>进入「ChatBI → 实验中心」，创建一个实验项目并关联已配置好的数据源和知识库。在实验室工作台中，你可以输入自然语言问题进行测试，系统会自动将问题解析为 SQL 查询并返回数据结果和可视化图表。利用追踪日志功能可以查看每次问答的完整执行链路（意图解析 → SQL 生成 → 数据查询 → 图表渲染），方便调优 Prompt 策略和知识配置。当实验效果达到预期后，即可将该实验配置用于正式环境。</p>
              </div>
            </div>
            <div class="step-row">
              <div class="step-num">5</div>
              <div>
                <strong>构建工作流</strong>
                <p>进入「工作流平台 → 我的工作流」，创建一个新的工作流应用。通过可视化工作流编排器，将实验中心验证过的分析能力编排成自动化流程：添加 LLM 节点处理用户意图，调用实验室工具执行数据查询，再通过条件分支控制不同场景的处理逻辑。搭建完成后，工作流可以作为独立的 AI 应用对外提供服务，实现从"人工提问"到"自动化分析"的跃升。</p>
              </div>
            </div>
          </div>
        </template>

        <!-- ChatBI 模块 -->
        <template v-if="activeSection === 'chatbi'">
          <div class="page-header">
            <h1>ChatBI 智能数据分析</h1>
            <p class="section-desc">ChatBI 是平台的核心模块，提供从数据接入到自然语言问答的完整数据分析链路。用户通过自然语言即可完成数据查询、多维分析与可视化。</p>
          </div>

          <h2>数据中心</h2>
          <div class="func-block">
            <p>管理所有业务数据库连接，是数据分析的基础。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>多数据库支持</strong> — 支持 MySQL、PostgreSQL 等主流关系型数据库的连接与管理</li>
              <li><strong>连接测试</strong> — 添加数据源后可一键测试连通性，确保配置正确</li>
              <li><strong>结构预览</strong> — 自动读取数据库表结构，方便后续知识库配置</li>
            </ul>
            <div class="tip-box">
              <strong>使用建议：</strong>建议为不同业务线分别创建数据源连接，便于后续权限管理和知识库隔离。
            </div>
          </div>

          <h2>知识引擎</h2>
          <div class="func-block">
            <p>精细化配置数据接入规则，提升问答准确度的关键环节。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>数据接入配置</strong> — 选择需要开放给问答系统的数据表，配置字段的中文描述和数据类型</li>
              <li><strong>表结构管理</strong> — 为每个字段添加业务含义说明，帮助模型准确理解列语义</li>
              <li><strong>知识词条</strong> — 定义业务术语和计算逻辑，例如"毛利率 = (收入-成本)/收入"</li>
              <li><strong>样例库</strong> — 添加典型问答样例，作为 few-shot 示例提升模型生成 SQL 的准确性</li>
            </ul>
            <div class="tip-box">
              <strong>使用建议：</strong>知识词条越丰富，问答准确率越高。建议优先添加含有专业计算逻辑的业务指标定义。
            </div>
          </div>

          <h2>知识中心</h2>
          <div class="func-block">
            <p>统一管理所有知识资产的集中平台，整合表结构、词条、样例和 NER 配置。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>知识库总览</strong> — 查看当前空间下所有知识资产的汇总统计</li>
              <li><strong>NER 实体识别</strong> — 配置命名实体识别规则，准确提取问题中的产品名、地区名等关键实体</li>
              <li><strong>批量管理</strong> — 支持知识词条和样例的批量导入导出</li>
            </ul>
          </div>

          <h2>聊天中心</h2>
          <div class="func-block">
            <p>核心交互界面，用户在此输入自然语言问题并获得数据分析结果。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>自然语言问答</strong> — 输入如"上季度各产品线营收对比"等业务问题，系统自动解析并返回结果</li>
              <li><strong>智能图表</strong> — 根据数据特征自动推荐柱状图、折线图、饼图等最佳可视化方式</li>
              <li><strong>多轮对话</strong> — 支持追问和上下文关联，如"再看看环比变化"</li>
              <li><strong>结果导出</strong> — 支持将分析结果导出为图片或数据表格</li>
            </ul>
            <div class="tip-box">
              <strong>提问技巧：</strong>问题越具体效果越好。建议包含明确的时间范围、维度和指标，例如"2024年Q1各区域的订单量和客单价"优于"看看销售情况"。
            </div>
          </div>

          <h2>实验中心</h2>
          <div class="func-block">
            <p>面向数据分析师的高级实验环境，用于测试和优化问答策略。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>实验项目</strong> — 创建独立的实验项目，对比不同 Prompt 策略和知识配置的效果</li>
              <li><strong>实验室工作台</strong> — 在可控环境中批量测试问答效果</li>
              <li><strong>追踪日志</strong> — 查看每个问答请求的完整执行链路：意图解析 → SQL 生成 → 数据查询 → 图表生成</li>
            </ul>
          </div>

          <h2>接口文档</h2>
          <div class="func-block">
            <p>系统 API 的完整文档，供开发人员集成使用。</p>
            <ul>
              <li>提供 RESTful API 接口规范</li>
              <li>包含认证方式和请求/响应示例</li>
              <li>支持在线调试和测试</li>
            </ul>
          </div>
        </template>

        <!-- 工作流模块 -->
        <template v-if="activeSection === 'agent'">
          <div class="page-header">
            <h1>工作流平台</h1>
            <p class="section-desc">工作流平台提供可视化的 AI 工作流编排能力，将大模型、工具和知识库组合成自动化分析流程。适用于需要多步骤推理和复杂业务逻辑的场景。</p>
          </div>

          <h2>工作流</h2>
          <div class="func-block">
            <p>创建和管理 AI 工作流应用。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>工作流创建</strong> — 通过表单或 AI Creator 对话式创建工作流，配置系统指令和参数</li>
              <li><strong>工作流设计</strong> — 拖拽式可视化编排器，支持 LLM 节点、条件分支、并行执行、循环等流程控制</li>
              <li><strong>版本管理</strong> — 每个工作流支持多版本管理，方便 A/B 测试和灰度发布</li>
              <li><strong>调试模式</strong> — 在工作流画布中实时调试，逐节点查看执行结果和中间变量</li>
            </ul>
            <div class="tip-box">
              <strong>使用建议：</strong>复杂分析任务建议拆分为多个子步骤，每个步骤使用独立的 LLM 节点处理，通过条件分支控制执行路径。
            </div>
          </div>

          <h2>工具管理</h2>
          <div class="func-block">
            <p>管理工作流中可调用的外部工具和内置能力。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>内置工具</strong> — 系统预置的数据查询、文件处理、HTTP 请求等基础工具</li>
              <li><strong>XLSX 智能问答</strong> — 专门针对 Excel 文件的智能分析工具，支持上传文件后用自然语言查询和可视化</li>
              <li><strong>自定义工具</strong> — 通过 API 接口注册自定义工具，扩展工作流能力</li>
            </ul>
          </div>

          <h2>知识库</h2>
          <div class="func-block">
            <p>为工作流提供外部知识检索能力（RAG）。</p>
            <ul>
              <li>支持上传文档（PDF、Word、TXT 等）构建知识库</li>
              <li>工作流在执行过程中自动检索相关知识片段</li>
              <li>支持多知识库挂载，按需为不同工作流配置专属知识源</li>
            </ul>
          </div>

          <h2>插件</h2>
          <div class="func-block">
            <p>通过插件机制扩展工作流平台能力。</p>
            <ul>
              <li>浏览和安装平台提供的扩展插件</li>
              <li>配置插件参数和权限</li>
              <li>支持开发自定义插件并发布到平台</li>
            </ul>
          </div>
        </template>

        <!-- 评测中心 -->
        <template v-if="activeSection === 'eval'">
          <div class="page-header">
            <h1>评测中心</h1>
            <p class="section-desc">评测中心用于量化评估 AI 问答效果，通过构建标准化评测集和自动化评测任务，持续跟踪和优化系统的准确率和可靠性。</p>
          </div>

          <h2>评测集</h2>
          <div class="func-block">
            <p>评测数据集的创建和管理。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>创建评测集</strong> — 定义标准问答对，包含用户问题和预期结果（SQL 或答案）</li>
              <li><strong>批量导入</strong> — 支持通过 Excel 批量导入评测用例，快速构建大规模评测集</li>
              <li><strong>标签分类</strong> — 按业务场景、难度等级为评测用例添加标签，方便筛选和统计</li>
            </ul>
            <div class="tip-box">
              <strong>使用建议：</strong>评测集应覆盖常见业务问题和边界场景。建议按照简单查询、聚合计算、多表关联、时间范围等维度分类构建。
            </div>
          </div>

          <h2>评测任务</h2>
          <div class="func-block">
            <p>执行评测并查看结果分析。</p>
            <h4>主要功能</h4>
            <ul>
              <li><strong>创建任务</strong> — 选择评测集和评测模板，配置评估参数后启动自动化评测</li>
              <li><strong>结果分析</strong> — 查看每条用例的评测结果：SQL 准确率、执行结果一致性、响应时间等</li>
              <li><strong>历史对比</strong> — 对比不同版本/配置下的评测结果，量化优化效果</li>
            </ul>
          </div>

          <h2>评测模板</h2>
          <div class="func-block">
            <p>标准化评测流程的模板管理。</p>
            <ul>
              <li>定义评测评分标准和判定规则</li>
              <li>支持模板复用，确保不同评测任务使用统一标准</li>
              <li>内置多种常用评测模板，可直接使用或基于其自定义</li>
            </ul>
          </div>
        </template>

        <!-- 系统管理 -->
        <template v-if="activeSection === 'management'">
          <div class="page-header">
            <h1>系统管理</h1>
            <p class="section-desc">系统管理模块提供平台运行所需的基础设施配置，包括 AI 模型服务、存储资源、用户权限和多租户空间管理。</p>
          </div>

          <h2>模型配置</h2>
          <div class="func-block">
            <h4>语言模型</h4>
            <p>配置大语言模型服务。支持接入 OpenAI、Azure OpenAI、文心一言、通义千问、DeepSeek 等服务商。添加后可配置 API 密钥、模型版本和并发限制。</p>
            <h4>向量模型</h4>
            <p>配置文本向量化（Embedding）模型，用于知识库的语义检索。支持 OpenAI Embedding、BGE 等主流向量模型。</p>
            <h4>多模态模型</h4>
            <p>配置支持图像理解等多模态能力的模型服务。</p>
          </div>

          <h2>存储与服务</h2>
          <div class="func-block">
            <h4>向量库</h4>
            <p>配置向量数据库（如 Milvus、Chroma 等），用于存储知识库的向量索引。</p>
            <h4>对象存储</h4>
            <p>配置 OSS/MinIO 等对象存储服务，用于文件上传和资源管理。</p>
            <h4>Elasticsearch</h4>
            <p>配置 ES 搜索引擎连接，用于日志检索和全文搜索功能。</p>
          </div>

          <h2>用户与权限</h2>
          <div class="func-block">
            <h4>用户管理</h4>
            <p>管理平台用户账号，包括创建用户、分配角色、启用/禁用账号等操作。支持管理员和普通用户两种角色。</p>
            <h4>空间管理</h4>
            <p>多租户空间隔离机制。不同空间的数据源、知识库、工作流等资源相互独立。管理员可创建空间、管理成员和配置资源配额。</p>
            <h4>审计日志</h4>
            <p>记录所有用户操作行为的审计追踪。支持按操作类型、用户、时间范围筛选查询，满足企业安全合规要求。</p>
          </div>
        </template>

        <!-- 更新日志 -->
        <template v-if="activeSection === 'changelog'">
          <div class="page-header">
            <h1>更新日志</h1>
            <p class="section-desc">记录平台各版本的功能更新与优化内容。</p>
          </div>

          <!-- v2.0.0 -->
          <div class="changelog-version major">
            <div class="version-header">
              <span class="version-tag major">v2.0.0</span>
              <span class="version-type major-release">Major Release</span>
              <span class="version-date">2026-05-06</span>
            </div>
            <div class="version-title">功能全面升级 · 智能分析新体验</div>
            <p class="version-summary">v2.0.0 是 AI4BI 平台的一次重大版本升级，涵盖深度洞察报告、智能工作流、XLSX 智能问答增强、评测中心等多项核心功能的全新发布与优化。</p>

            <div class="change-group">
              <div class="change-category feature">
                <span class="category-badge">NEW</span>
                <span>新功能</span>
              </div>
              <ul>
                <li><strong>深度洞察报告</strong> — 一键生成包含数据摘要、趋势分析、关键发现的深度分析报告，支持导出为 PPT 和 PDF 格式</li>
                <li><strong>PPT 报告导出</strong> — 分析结果一键导出为专业 PPT 报告，支持多模板切换、自定义 Logo，含原生图表和数据摘要，导出任务异步执行不阻塞操作</li>
                <li><strong>PDF 报告导出</strong> — 支持将分析结果和洞察报告导出为 PDF 文档，导出文件自动同步至工作台和分享页</li>
                <li><strong>XLSX 智能问答</strong> — 上传 Excel 文件即可用自然语言提问，自动解析表结构、生成 SQL 并返回可视化结果，支持 SSE 流式输出实时呈现分析过程</li>
                <li><strong>AI Creator 工作流创建器</strong> — 通过自然语言对话即可创建和配置工作流，降低工作流搭建门槛</li>
                <li><strong>工作流并行节点</strong> — 支持工作流中多个节点并行执行，复杂任务处理效率显著提升</li>
                <li><strong>原子能力</strong> — 将常用数据分析操作封装为可复用的原子能力，可在工作流中灵活调用</li>
                <li><strong>知识中心 NER 实体识别</strong> — 自动识别问题中的产品名、地区名等实体，提升 SQL 生成准确率</li>
                <li><strong>多空间管理</strong> — 支持按部门或项目创建独立空间，各空间的数据源、知识库、工作流等资源完全隔离</li>
              </ul>
            </div>

            <div class="change-group">
              <div class="change-category improve">
                <span class="category-badge">IMPROVED</span>
                <span>优化</span>
              </div>
              <ul>
                <li>SQL 生成管线优化，引入 Plan-Execute 两阶段策略，复杂查询准确率显著提升</li>
                <li>工作流画布体验优化，解决节点拖动粘连问题，支持画布缩放与小地图导航</li>
                <li>评测中心全面增强，新增评测模板引擎、批量评测、结果可视化对比</li>
                <li>知识库管理功能增强，支持知识词条、样例库的批量管理与 NER 规则配置</li>
                <li>审计日志系统优化，新增高级筛选能力，支持按操作类型、用户、时间范围查询</li>
                <li>工作流 SSE 流式输出优化，思考过程实时透传，SQL 提取更加准确</li>
                <li>API 文档改版，采用全新交互式文档界面，支持在线调试</li>
                <li>聊天中心交互优化，支持多轮对话追问和上下文关联</li>
              </ul>
            </div>

            <div class="change-group">
              <div class="change-category security">
                <span class="category-badge">SECURITY</span>
                <span>安全</span>
              </div>
              <ul>
                <li>SQL 注入防护升级，新增多层 SQL 安全检查机制，严格限制 DDL/DML 操作</li>
                <li>API 鉴权体系增强，基于 JWT Token + RBAC 权限模型实现细粒度访问控制</li>
                <li>默认空间保护机制，防止误删系统关键配置</li>
              </ul>
            </div>
          </div>

          <!-- v1.5.5 -->
          <div class="changelog-version minor">
            <div class="version-header">
              <span class="version-tag minor">v1.5.5</span>
              <span class="version-type patch-release">Patch</span>
              <span class="version-date">2026-03-20</span>
            </div>
            <div class="version-title">稳定性修复</div>

            <div class="change-group">
              <div class="change-category fix">
                <span class="category-badge">FIX</span>
                <span>修复</span>
              </div>
              <ul>
                <li>修复聊天中心在高并发场景下偶发的 WebSocket 连接中断问题</li>
                <li>修复知识词条编辑页面保存后未及时刷新列表的缓存问题</li>
                <li>修复评测任务在部分边界用例下评分计算不准确的问题</li>
                <li>修复数据源连接测试超时时未正确返回错误提示的问题</li>
              </ul>
            </div>

            <div class="change-group">
              <div class="change-category improve">
                <span class="category-badge">IMPROVED</span>
                <span>优化</span>
              </div>
              <ul>
                <li>聊天对话列表加载性能优化，历史记录加载速度提升 30%</li>
                <li>数据源列表页增加连接状态实时检测指示器</li>
              </ul>
            </div>
          </div>

          <!-- v1.5.4 -->
          <div class="changelog-version minor">
            <div class="version-header">
              <span class="version-tag minor">v1.5.4</span>
              <span class="version-type patch-release">Patch</span>
              <span class="version-date">2026-02-28</span>
            </div>
            <div class="version-title">兼容性改进</div>

            <div class="change-group">
              <div class="change-category fix">
                <span class="category-badge">FIX</span>
                <span>修复</span>
              </div>
              <ul>
                <li>修复 PostgreSQL 数据源在特定字符编码下表结构读取失败的问题</li>
                <li>修复工作流在包含中文变量名时解析异常的问题</li>
                <li>修复审计日志分页查询在大数据量下的性能退化问题</li>
              </ul>
            </div>

            <div class="change-group">
              <div class="change-category improve">
                <span class="category-badge">IMPROVED</span>
                <span>优化</span>
              </div>
              <ul>
                <li>向量模型配置页面增加模型可用性预检测</li>
                <li>优化大文件上传时的内存占用，支持最大 200MB 的 Excel 文件</li>
              </ul>
            </div>
          </div>
        </template>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import {
  House,
  DataAnalysis,
  Cpu,
  Collection,
  Setting,
  Clock
} from '@element-plus/icons-vue'

const activeSection = ref('overview')

const navSections = [
  { key: 'overview', label: '产品概述', icon: House },
  { key: 'chatbi', label: 'ChatBI 数据分析', icon: DataAnalysis },
  { key: 'agent', label: '工作流平台', icon: Cpu },
  { key: 'eval', label: '评测中心', icon: Collection },
  { key: 'management', label: '系统管理', icon: Setting },
  { key: 'changelog', label: '更新日志', icon: Clock }
]
</script>

<style scoped>
.help-center-layout {
  display: flex;
  height: 100%;
  background: #fafbfc;
}

/* ===== 左侧导航 ===== */
.help-sidebar {
  width: 200px;
  min-width: 200px;
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
}

.sidebar-nav {
  flex: 1;
  padding: 16px 10px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13.5px;
  transition: all 0.15s ease;
  margin-bottom: 4px;
  color: #606266;
}

.nav-item:hover {
  background: #f5f7fa;
  color: #303133;
}

.nav-item.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.nav-item .el-icon {
  font-size: 17px;
  flex-shrink: 0;
}

/* ===== 右侧内容 ===== */
.help-content {
  flex: 1;
  overflow-y: auto;
  padding: 48px 56px;
}

.content-inner {
  max-width: 920px;
}

/* 页面标题区域 */
.page-header {
  margin-bottom: 40px;
}

.page-header h1 {
  font-size: 30px;
  font-weight: 700;
  color: #1d2129;
  margin: 0 0 12px 0;
  letter-spacing: -0.3px;
}

.section-desc {
  font-size: 15px;
  color: #86909c;
  line-height: 1.8;
  margin: 0;
}

h1 {
  font-size: 30px;
  font-weight: 700;
  color: #1d2129;
  margin: 0 0 12px 0;
  letter-spacing: -0.3px;
}

h2 {
  font-size: 19px;
  font-weight: 600;
  color: #1d2129;
  margin: 40px 0 14px 0;
  padding-bottom: 10px;
  border-bottom: 1px solid #ebeef5;
}

h2:first-of-type {
  margin-top: 0;
}

.h2-desc {
  font-size: 14px;
  color: #86909c;
  line-height: 1.7;
  margin: -6px 0 20px 0;
}

/* ===== 概述页 ===== */
.highlight-card {
  background: linear-gradient(135deg, var(--el-color-primary-light-9) 0%, var(--el-color-primary-light-8) 50%, #fff 100%);
  border: 1px solid var(--el-color-primary-light-7);
}

.info-card {
  border-radius: 14px;
  padding: 32px;
  margin-bottom: 36px;
}

.info-card h3 {
  font-size: 17px;
  font-weight: 600;
  color: #1d2129;
  margin: 0 0 24px 0;
}

.value-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 28px;
}

.value-item {
  text-align: center;
  padding: 12px 0;
}

.value-num {
  font-size: 38px;
  font-weight: 800;
  color: var(--el-color-primary);
  line-height: 1;
  margin-bottom: 8px;
}

.value-label {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
  margin-bottom: 6px;
}

.value-item p {
  font-size: 13px;
  color: #86909c;
  margin: 0;
  line-height: 1.6;
}

.arch-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin-bottom: 32px;
}

.arch-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.arch-item:hover {
  border-color: var(--el-color-primary-light-3);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
  transform: translateY(-1px);
}

.arch-item strong {
  font-size: 14.5px;
  color: #1d2129;
  display: block;
  margin-bottom: 4px;
}

.arch-item p {
  font-size: 13px;
  color: #86909c;
  margin: 0;
  line-height: 1.6;
}

.arch-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 6px;
  margin-top: 1px;
  letter-spacing: 0.3px;
}

.arch-badge.chatbi { background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.arch-badge.agent { background: #fff0f6; color: #c41d7f; }
.arch-badge.eval { background: #f6ffed; color: #389e0d; }
.arch-badge.mgmt { background: #fff7e6; color: #d46b08; }

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 32px;
}

.step-row {
  display: flex;
  gap: 18px;
  align-items: flex-start;
  padding: 22px 24px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  transition: box-shadow 0.2s ease;
}

.step-row:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.step-num {
  width: 32px;
  height: 32px;
  background: var(--el-color-primary);
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 1px;
}

.step-row strong {
  font-size: 15px;
  color: #1d2129;
  display: block;
  margin-bottom: 6px;
}

.step-row p {
  font-size: 13.5px;
  color: #606266;
  margin: 0;
  line-height: 1.75;
}

/* ===== 功能模块通用 ===== */
.func-block {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 18px;
  transition: box-shadow 0.2s ease;
}

.func-block:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.03);
}

.func-block > p:first-child {
  margin: 0 0 16px 0;
  font-size: 14px;
  color: #606266;
  line-height: 1.7;
}

.func-block h4 {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
  margin: 16px 0 10px 0;
}

.func-block h4:first-child,
.func-block > p:first-child + h4 {
  margin-top: 0;
}

.func-block ul {
  margin: 0;
  padding-left: 18px;
}

.func-block li {
  font-size: 13.5px;
  color: #4e5969;
  line-height: 1.8;
  margin-bottom: 6px;
}

.func-block li strong {
  color: #1d2129;
}

.tip-box {
  margin-top: 18px;
  padding: 14px 18px;
  background: var(--el-color-primary-light-9);
  border-left: 3px solid var(--el-color-primary);
  border-radius: 0 8px 8px 0;
  font-size: 13.5px;
  color: #4e5969;
  line-height: 1.7;
}

.tip-box strong {
  color: var(--el-color-primary);
}

/* ===== 更新日志 ===== */
.changelog-version {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 14px;
  padding: 28px 32px;
  margin-bottom: 24px;
}

.changelog-version.major {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 4px 20px rgba(31, 184, 204, 0.06);
}

.version-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.version-tag {
  font-size: 17px;
  font-weight: 800;
  padding: 4px 14px;
  border-radius: 8px;
}

.version-tag.major {
  background: var(--el-color-primary);
  color: #fff;
}

.version-tag.minor {
  background: #f0f0f5;
  color: #606266;
}

.version-type {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 3px 10px;
  border-radius: 4px;
}

.major-release {
  background: #fff7e6;
  color: #d46b08;
}

.patch-release {
  background: #f5f5f5;
  color: #909399;
}

.version-date {
  font-size: 13px;
  color: #c0c4cc;
  margin-left: auto;
}

.version-title {
  font-size: 22px;
  font-weight: 700;
  color: #1d2129;
  margin-bottom: 8px;
}

.version-summary {
  font-size: 14px;
  color: #606266;
  line-height: 1.7;
  margin: 0 0 24px 0;
}

.change-group {
  margin-bottom: 20px;
}

.change-group:last-child {
  margin-bottom: 0;
}

.change-category {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #4e5969;
}

.category-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding: 3px 8px;
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
}

.change-category.breaking .category-badge { background: #fff1f0; color: #cf1322; }
.change-category.feature .category-badge { background: #f6ffed; color: #389e0d; }
.change-category.improve .category-badge { background: var(--el-color-primary-light-9); color: var(--el-color-primary-dark-2); }
.change-category.fix .category-badge { background: #fffbe6; color: #d48806; }
.change-category.security .category-badge { background: #fff0f6; color: #c41d7f; }

.change-group ul {
  margin: 0;
  padding-left: 18px;
}

.change-group li {
  font-size: 13.5px;
  color: #4e5969;
  line-height: 1.8;
  margin-bottom: 5px;
}

.change-group li strong {
  color: #1d2129;
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .help-center-layout {
    flex-direction: column;
  }

  .help-sidebar {
    width: 100%;
    min-width: auto;
    flex-direction: row;
    overflow-x: auto;
    border-right: none;
    border-bottom: 1px solid #ebeef5;
  }

  .sidebar-nav {
    display: flex;
    padding: 8px;
    gap: 4px;
  }

  .nav-item {
    white-space: nowrap;
    margin-bottom: 0;
  }

  .help-content {
    padding: 24px 20px;
  }

  .value-grid {
    grid-template-columns: 1fr;
  }

  .arch-list {
    grid-template-columns: 1fr;
  }
}
</style>
