<template>
  <div v-loading="loading" class="agent-workflow-page">
    <header class="agent-workflow-top">
      <div class="agent-workflow-top__left">
        <el-button text type="primary" class="agent-workflow-back" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <div class="agent-workflow-title-block">
          <h1 class="agent-workflow-title">{{ app?.name || '工作流' }}</h1>
          <span class="agent-workflow-sub">
            {{ version?.name || '版本' }}
            <el-tag v-if="version" size="small" class="agent-workflow-status-tag" :type="statusTagType">
              {{ statusLabel }}
            </el-tag>
          </span>
        </div>
      </div>
      <div class="agent-workflow-top__center" role="tablist" aria-label="工作流与测试">
        <span class="agent-workflow-pill-tab is-active" aria-current="page">
          {{ loading ? '加载工作流…' : workflowReadonly ? '工作流详情' : '工作流设计' }}
        </span>
        <router-link
          class="agent-workflow-pill-tab"
          :to="{ name: 'AgentWorkflowDebug', params: { appId, versionId }, query: route.query }"
        >
          效果测试
        </router-link>
      </div>
      <div class="agent-workflow-top__right">
        <template v-if="!workflowReadonly">
          <el-button
            size="small"
            class="agent-workflow-toolbar-btn agent-workflow-toolbar-btn--save"
            :loading="savingWorkflow"
            :disabled="!hasUnsavedChanges && !savingWorkflow"
            @click="saveNow"
          >
            {{ savingWorkflow ? '保存中…' : hasUnsavedChanges ? '保存' : '已保存' }}
          </el-button>
          <el-tooltip content="自动整理布局（从左到右分层）" placement="bottom">
            <el-button
              size="small"
              class="agent-workflow-toolbar-btn agent-workflow-toolbar-btn--minor"
              :loading="arrangingLayout"
              @click="arrangeWorkflowLayout"
            >
              整理布局
            </el-button>
          </el-tooltip>
          <el-tooltip content="撤销 (⌘/Ctrl+Z)" placement="bottom">
            <el-button
              size="small"
              class="agent-workflow-toolbar-btn agent-workflow-toolbar-btn--minor"
              :disabled="!canUndo"
              @click="undo"
            >
              <el-icon><RefreshLeft /></el-icon>
              上一步
            </el-button>
          </el-tooltip>
          <el-tooltip content="重做 (⌘/Ctrl+Shift+Z)" placement="bottom">
            <el-button
              size="small"
              class="agent-workflow-toolbar-btn agent-workflow-toolbar-btn--minor"
              :disabled="!canRedo"
              @click="redo"
            >
              <el-icon><RefreshRight /></el-icon>
              下一步
            </el-button>
          </el-tooltip>
          <el-dropdown trigger="click" popper-class="agent-workflow-node-dropdown" @command="addPaletteNode">
            <el-button size="small" class="agent-workflow-toolbar-btn agent-workflow-toolbar-btn--minor">
              <el-icon><Plus /></el-icon>
              添加节点
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu class="agent-workflow-node-menu">
                <el-dropdown-item v-for="item in paletteForMenu" :key="item.kind" :command="item.kind">
                  <span class="agent-workflow-node-menu__row">
                    <span class="agent-workflow-node-menu__icon" :class="`is-${item.kind}`">
                      <el-icon><component :is="paletteIcon(item.kind)" /></el-icon>
                    </span>
                    {{ item.label }}
                  </span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
        <el-tag v-else-if="!loading && version" type="info" size="small" class="agent-workflow-readonly-tag" effect="plain">
          只读查看
        </el-tag>
        <el-button class="agent-workflow-toolbar-btn agent-workflow-toolbar-btn--debug" :disabled="loading" @click="goToDebugMode">
          <el-icon><Monitor /></el-icon>
          调试模式
        </el-button>
        <el-button v-if="!workflowReadonly" type="primary" class="agent-workflow-publish" @click="publishWorkflow">
          <el-icon><Promotion /></el-icon>
          发布
        </el-button>
      </div>
    </header>

    <div class="agent-workflow-body">
      <div class="agent-workflow-canvas-wrap">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          :edge-types="edgeTypes"
          :default-edge-options="defaultEdgeOptions"
          :snap-to-grid="true"
          :snap-grid="[12, 12]"
          :min-zoom="0.1"
          :max-zoom="1.5"
          :nodes-draggable="!workflowReadonly"
          :nodes-connectable="!workflowReadonly"
          :edges-updatable="!workflowReadonly"
          @connect="onConnect"
          @node-click="onNodeClick"
          @pane-click="onPaneClick"
          @node-drag-stop="onNodeDragStop"
          @selection-drag-stop="onSelectionDragStop"
        >
          <Background variant="dots" :gap="16" :size="1" color="#d0d5dd" />
          <Controls position="bottom-right" />
          <MiniMap pannable zoomable position="bottom-left" class="agent-workflow-minimap" />
        </VueFlow>
      </div>

      <aside
        v-if="selectedNode"
        class="agent-workflow-inspector"
        :style="{ width: 'min(680px, 55vw)', minWidth: 'min(440px, 50vw)' }"
        aria-label="节点配置"
      >
        <div class="agent-workflow-inspector__head">
            <div class="agent-workflow-inspector__title-row">
              <span class="agent-workflow-inspector__icon">
                <el-icon><component :is="inspectorIcon" /></el-icon>
              </span>
              <el-input
                v-model="inspectorLabelDraft"
                class="agent-workflow-inspector__title-input"
                :placeholder="inspectorDefaultTitle"
                :disabled="workflowReadonly || inspectorKind === 'start'"
                @blur="commitNodeLabel"
              />
              <el-button text circle @click="clearSelection">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
            <el-input
              v-if="inspectorKind !== 'start'"
              v-model="nodeDescription"
              type="textarea"
              :rows="2"
              placeholder="添加描述..."
              resize="none"
              class="agent-workflow-inspector__desc"
              :disabled="workflowReadonly"
              @blur="persistNodeDescription"
            />
          </div>
          <fieldset class="agent-workflow-inspector__fieldset" :disabled="workflowReadonly">
          <div class="agent-workflow-inspector__settings">
            <el-alert v-if="selectedNodeIssues.length" type="warning" :closable="false" show-icon title="配置待完善" class="workflow-validation">
              <ul><li v-for="issue in selectedNodeIssues" :key="issue">{{ issue }}</li></ul>
            </el-alert>
              <p v-if="inspectorKind === 'start'" class="agent-workflow-inspector__hint">
                「开始」节点仅作流程起点标识，无需配置。
              </p>

              <template v-if="inspectorKind === 'userInput'">
                <el-collapse v-model="userInputCollapse" class="agent-workflow-userinput-collapse">
                  <el-collapse-item title="入参" name="params">
                    <div class="user-input-params">
                      <div
                        v-for="(row, idx) in userInputFieldRows"
                        :key="idx"
                        class="user-input-params__row"
                      >
                        <div class="user-input-params__line user-input-params__line--name">
                          <span class="user-input-params__line-label">名称</span>
                          <el-input v-model="row.variable" size="small" placeholder="如 input" @change="commitUserInputFields" />
                          <el-button
                            text
                            type="danger"
                            size="small"
                            class="user-input-params__remove"
                            :disabled="userInputFieldRows.length <= 1"
                            @click="removeUserInputFieldRow(idx)"
                          >
                            删除
                          </el-button>
                        </div>
                        <div class="user-input-params__line user-input-params__line--source">
                          <span class="user-input-params__line-label">来源</span>
                          <div class="user-input-params__source-pair">
                            <el-select
                              v-model="row.source_mode"
                              size="small"
                              class="user-input-params__source-mode"
                              @change="onUserInputSourceMode(row)"
                            >
                              <el-option
                                v-for="opt in userInputSourceModeOptions"
                                :key="opt.value"
                                :label="opt.label"
                                :value="opt.value"
                              />
                            </el-select>
                            <el-input
                              v-if="row.source_mode !== 'ref'"
                              v-model="row.default"
                              size="small"
                              placeholder="默认值"
                              @blur="commitUserInputFields"
                            />
                          </div>
                          <el-cascader
                            v-if="row.source_mode === 'ref'"
                            v-model="row.source_ref"
                            :options="userInputSourceCascaderOptions"
                            :props="{ expandTrigger: 'hover' }"
                            clearable
                            class="user-input-params__cascader"
                            @change="commitUserInputFields"
                          />
                        </div>
                        <div class="user-input-params__line user-input-params__line--type">
                          <span class="user-input-params__line-label">类型</span>
                          <div class="user-input-params__type-row">
                            <el-select v-model="row.type" size="small" style="width: 100%" @change="commitUserInputFields">
                              <el-option
                                v-for="opt in userInputFieldTypeOptions"
                                :key="opt.value"
                                :label="opt.label"
                                :value="opt.value"
                              />
                            </el-select>
                            <el-checkbox v-model="row.required" @change="commitUserInputFields">必填</el-checkbox>
                          </div>
                        </div>
                      </div>
                    </div>
                    <el-button text type="primary" size="small" class="user-input-params__add" @click="addUserInputFieldRow">
                      ＋ 添加字段
                    </el-button>
                  </el-collapse-item>
                </el-collapse>
              </template>

              <template v-else-if="inspectorKind === 'output'">
                <el-collapse v-model="outputCollapse" class="agent-workflow-userinput-collapse">
                  <el-collapse-item title="Content（内容）" name="content">
                    <div class="user-input-params">
                      <div v-for="(row, idx) in outputContentRows" :key="`out-c-${idx}`" class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <span class="user-input-params__line-label">格式</span>
                          <el-select v-model="row.output_format" size="small" style="width: 100px" @change="commitOutputTemplate">
                            <el-option label="text" value="text" />
                            <el-option label="json" value="json" />
                            <el-option label="markdown" value="markdown" />
                          </el-select>
                          <el-button
                            text
                            type="danger"
                            size="small"
                            class="user-input-params__remove"
                            @click="removeOutputContentRow(idx)"
                          >
                            删除
                          </el-button>
                        </div>
                        <div class="user-input-params__line user-input-params__line--source">
                          <span class="user-input-params__line-label">来源</span>
                          <div class="user-input-params__source-pair">
                            <el-select v-model="row.source_mode" size="small" class="user-input-params__source-mode" @change="commitOutputTemplate">
                              <el-option v-for="opt in userInputSourceModeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                            <el-input
                              v-if="row.source_mode !== 'ref'"
                              v-model="row.const_value"
                              size="small"
                              placeholder="常量值"
                              @blur="commitOutputTemplate"
                            />
                            <el-select
                              v-else
                              v-model="row.source_ref"
                              filterable
                              allow-create
                              size="small"
                              placeholder="如 LLM.text"
                              @change="commitOutputTemplate"
                            >
                              <el-option v-for="opt in upstreamVarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                          </div>
                        </div>
                      </div>
                      <el-button text type="primary" size="small" @click="addOutputContentRow">
                        + 添加字段
                      </el-button>
                    </div>
                  </el-collapse-item>
                  <el-collapse-item title="Metadata（元数据）" name="metadata">
                    <div class="user-input-params">
                      <div v-for="(row, idx) in outputMetadataRows" :key="`out-m-${idx}`" class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <span class="user-input-params__line-label">名称</span>
                          <el-input v-model="row.name" size="small" placeholder="如 trace_id" @change="commitOutputTemplate" />
                          <el-select v-model="row.type" size="small" style="width: 100px" @change="commitOutputTemplate">
                            <el-option label="STRING" value="STRING" />
                            <el-option label="NUMBER" value="NUMBER" />
                            <el-option label="BOOLEAN" value="BOOLEAN" />
                            <el-option label="ARRAY" value="ARRAY" />
                            <el-option label="OBJECT" value="OBJECT" />
                          </el-select>
                          <el-button
                            text
                            type="danger"
                            size="small"
                            class="user-input-params__remove"
                            @click="removeOutputMetadataRow(idx)"
                          >
                            删除
                          </el-button>
                        </div>
                        <div class="user-input-params__line user-input-params__line--source">
                          <span class="user-input-params__line-label">来源</span>
                          <div class="user-input-params__source-pair">
                            <el-select v-model="row.source_mode" size="small" class="user-input-params__source-mode" @change="commitOutputTemplate">
                              <el-option v-for="opt in userInputSourceModeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                            <el-select
                              v-if="row.source_mode === 'ref'"
                              v-model="row.source_ref"
                              filterable
                              allow-create
                              size="small"
                              placeholder="如 用户输入.input"
                              @change="commitOutputTemplate"
                            >
                              <el-option v-for="opt in upstreamVarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                            <el-input v-else v-model="row.const_value" size="small" :placeholder="constantPlaceholder(row.type)" @blur="commitOutputTemplate" />
                          </div>
                        </div>
                      </div>
                      <el-button text type="primary" size="small" @click="addOutputMetadataRow">
                        + 添加字段
                      </el-button>
                    </div>
                  </el-collapse-item>
                  <el-collapse-item title="高级配置" name="advanced">
                    <div class="wf-insp-field">
                      <span class="wf-insp-field__label">输出模板</span>
                      <p class="wf-insp-field__hint">使用 <code v-pre>{{节点名称.字段}}</code> 引用上游。配置 Content 内容字段时优先使用内容字段；未配置时使用此模板。</p>
                      <el-input
                        v-model="outputTemplateDraft"
                        type="textarea"
                        :rows="3"
                        placeholder="例如：{{LLM.text}}"
                        @blur="commitOutputTemplate"
                      />
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </template>

              <template v-else-if="inspectorKind === 'llm'">
                <div class="wf-insp-panel wf-insp-panel--llm">
                  <div class="wf-insp-callout wf-insp-callout--compact">
                    <span class="wf-insp-callout__icon" aria-hidden="true">
                      <el-icon><InfoFilled /></el-icon>
                    </span>
                    <p class="wf-insp-callout__text">
                      节点输出为 <code>text</code>。系统提示词非空时作为 <code>system</code> 发送。
                      关闭「自定义用户提示词」时，<code>user</code> 使用第一个已绑定输入；没有输入时使用系统提示词。
                      开启后按用户提示词生成 <code>user</code>；均支持 <code v-pre>{{节点.字段}}</code> 与
                      <code v-pre>{{input}}</code> 等命名占位。
                    </p>
                  </div>
                  <el-collapse v-model="llmCollapse" class="agent-workflow-userinput-collapse wf-insp-collapse">
                    <el-collapse-item title="模型与采样" name="model">
                      <div class="wf-insp-field">
                        <span class="wf-insp-field__label">模型供应商</span>
                        <el-select
                          v-model="llmDraft.provider_id"
                          filterable
                          placeholder="选择供应商"
                          style="width: 100%"
                          @change="onLlmProviderChange"
                        >
                          <el-option v-for="p in modelProviders" :key="p.id" :label="p.name" :value="p.id" />
                        </el-select>
                      </div>
                      <div class="wf-insp-field">
                        <span class="wf-insp-field__label">模型名称</span>
                        <el-select
                          v-model="llmDraft.model_name"
                          filterable
                          allow-create
                          placeholder="模型"
                          style="width: 100%"
                          @change="commitLlmConfig"
                        >
                          <el-option v-for="m in llmModelOptions" :key="m" :label="m" :value="m" />
                        </el-select>
                      </div>
                      <div class="wf-insp-field wf-insp-field--grid2">
                        <div class="wf-inp-subfield">
                          <span class="wf-insp-field__label">温度</span>
                          <el-input-number
                            v-model="llmDraft.temperature"
                            :min="0"
                            :max="2"
                            :step="0.1"
                            size="small"
                            class="wf-inp-subfield__control"
                            @change="commitLlmConfig"
                          />
                        </div>
                        <div class="wf-inp-subfield">
                          <span class="wf-insp-field__label">max_tokens</span>
                          <el-input-number
                            v-model="llmDraft.max_tokens"
                            :min="1"
                            :max="128000"
                            :step="100"
                            size="small"
                            class="wf-inp-subfield__control"
                            @change="commitLlmConfig"
                          />
                        </div>
                      </div>
                    </el-collapse-item>
                    <el-collapse-item title="输入参数 (高级)" name="inputParams">
                      <div class="user-input-params">
                        <div v-for="(row, idx) in llmInputParamRows" :key="`llm-in-${idx}`" class="user-input-params__row">
                          <div class="user-input-params__line user-input-params__line--name">
                            <span class="user-input-params__line-label">占位</span>
                            <el-input v-model="row.variable" size="small" placeholder="如 input" @change="commitLlmInputParams" />
                            <el-button
                              text
                              type="danger"
                              size="small"
                              class="user-input-params__remove"
                              :disabled="llmInputParamRows.length <= 1"
                              @click="removeLlmInputParamRow(idx)"
                            >
                              删除
                            </el-button>
                          </div>
                          <div class="user-input-params__line user-input-params__line--source">
                            <span class="user-input-params__line-label">来源</span>
                            <div class="user-input-params__source-pair">
                              <el-select
                                v-model="row.source_mode"
                                size="small"
                                class="user-input-params__source-mode"
                                @change="commitLlmInputParams"
                              >
                                <el-option
                                  v-for="opt in userInputSourceModeOptions"
                                  :key="opt.value"
                                  :label="opt.label"
                                  :value="opt.value"
                                />
                              </el-select>
                              <el-input
                                v-if="row.source_mode !== 'ref'"
                                v-model="row.default"
                                size="small"
                                placeholder="默认值"
                                @blur="commitLlmInputParams"
                              />
                              <el-select
                                v-else
                                v-model="row.ref"
                                filterable
                                allow-create
                                size="small"
                                placeholder="如 用户输入.input"
                                @change="commitLlmInputParams"
                              >
                                <el-option
                                  v-for="opt in upstreamVarOptions"
                                  :key="opt.value"
                                  :label="opt.label"
                                  :value="opt.value"
                                />
                              </el-select>
                            </div>
                          </div>
                        </div>
                        <el-button text type="primary" size="small" @click="addLlmInputParamRow">
                          + 添加字段
                        </el-button>
                      </div>
                    </el-collapse-item>
                    <el-collapse-item title="高级配置" name="advanced">
                      <div class="wf-insp-field">
                        <span class="wf-insp-field__label">停止词</span>
                        <p class="wf-insp-field__hint">模型遇到停止词时停止生成（每行一个）</p>
                        <el-input
                          v-model="llmStopWordsText"
                          type="textarea"
                          :rows="3"
                          placeholder="每行一个停止词，如：\n观察结束\n回答完毕"
                          @blur="commitLlmStopWords"
                        />
                      </div>
                      <p class="wf-insp-field__hint">模型调用失败立即结束，不自动重试。</p>
                    </el-collapse-item>
                    <el-collapse-item title="输出参数" name="outputParams">
                      <div class="wf-atomic-output-chips">
                        <el-tag v-for="row in LLM_OUTPUT_FIELDS" :key="row.variable" type="info">{{ row.variable }} · {{ row.type }}</el-tag>
                      </div>
                      <p class="agent-workflow-script-hint">模型生成内容通过 text 返回；执行错误在效果测试的节点日志中查看。</p>
                    </el-collapse-item>
                    <el-collapse-item title="提示词与消息" name="prompt">
                      <div class="wf-insp-field wf-insp-field--flush">
                        <span class="wf-insp-field__label">系统提示词</span>
                        <p class="wf-insp-field__hint">
                          支持 <code v-pre>{{节点名称.字段}}</code>；英文标识的
                          <code v-pre>{{input}}</code> 等需在下方绑定。非空内容始终作为 <code>system</code> 发送；
                          用户消息由输入参数或下方用户提示词生成。
                        </p>
                        <el-input
                          v-model="llmDraft.system_prompt"
                          type="textarea"
                          :rows="5"
                          class="wf-insp-prompt-textarea"
                          placeholder="例如：你是助手。用户问题：{{input}}"
                          @blur="commitLlmConfig"
                        />
                      </div>
                      <div v-if="llmNamedSlotKeys.length" class="wf-insp-field">
                        <span class="wf-insp-field__label">命名参数</span>
                        <p class="wf-insp-field__hint">为系统/用户提示词中出现的 <code v-pre>{{英文标识}}</code> 指定来源。</p>
                        <div class="user-input-params">
                          <div
                            v-for="name in llmNamedSlotKeys"
                            :key="'llm-slot-' + name"
                            class="user-input-params__row"
                          >
                            <div class="user-input-params__line user-input-params__line--name">
                              <span class="user-input-params__line-label">占位</span>
                              <el-input :model-value="name" disabled size="small" />
                            </div>
                            <div class="user-input-params__line user-input-params__line--source">
                              <span class="user-input-params__line-label">来源</span>
                              <div class="user-input-params__source-pair">
                                <el-select
                                  v-model="llmDraft.param_bindings[name].source_mode"
                                  size="small"
                                  class="user-input-params__source-mode"
                                  @change="commitLlmConfig"
                                >
                                  <el-option
                                    v-for="opt in userInputSourceModeOptions"
                                    :key="opt.value"
                                    :label="opt.label"
                                    :value="opt.value"
                                  />
                                </el-select>
                                <el-select
                                  v-if="llmDraft.param_bindings[name].source_mode === 'ref'"
                                  v-model="llmDraft.param_bindings[name].ref"
                                  filterable
                                  allow-create
                                  size="small"
                                  placeholder="如 用户输入.query"
                                  @change="commitLlmConfig"
                                >
                                  <el-option
                                    v-for="opt in upstreamVarOptions"
                                    :key="opt.value"
                                    :label="opt.label"
                                    :value="opt.value"
                                  />
                                </el-select>
                                <el-input
                                  v-else
                                  v-model="llmDraft.param_bindings[name].const_value"
                                  size="small"
                                  placeholder="常量值"
                                  @blur="commitLlmConfig"
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div class="wf-insp-field wf-insp-field--switch-row">
                        <span class="wf-insp-field__label">自定义用户提示词</span>
                        <el-switch v-model="llmDraft.use_user_prompt_template" @change="onLlmUserPromptSwitch" />
                      </div>
                      <div v-if="llmDraft.use_user_prompt_template" class="wf-insp-field wf-insp-field--flush">
                        <span class="wf-insp-field__label">用户提示词</span>
                        <p class="wf-insp-field__hint">
                          与系统提示词共用变量绑定。包含占位符时按模板替换；不含占位符时在文字后追加第一个已绑定输入；留空则使用该输入。
                        </p>
                        <el-input
                          v-model="llmDraft.user_prompt"
                          type="textarea"
                          :rows="5"
                          class="wf-insp-prompt-textarea"
                          placeholder="例如：请处理：{{input}}"
                          @blur="commitLlmConfig"
                        />
                      </div>
                    </el-collapse-item>
                  </el-collapse>
                </div>
              </template>

              <template v-else-if="inspectorKind === 'script'">
                <el-collapse v-model="scriptCollapse" class="agent-workflow-userinput-collapse">
                  <el-collapse-item title="输入变量" name="in">
                    <div class="user-input-params">
                      <div v-for="(row, idx) in scriptInputRows" :key="`sin-${idx}`" class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <span class="user-input-params__line-label">名称</span>
                          <el-input v-model="row.name" size="small" placeholder="参数名" @change="commitScriptParams" />
                          <el-button text type="danger" size="small" class="user-input-params__remove" @click="removeScriptInputRow(idx)">删除</el-button>
                        </div>
                        <div class="user-input-params__line user-input-params__line--source">
                          <span class="user-input-params__line-label">来源</span>
                          <div class="user-input-params__source-pair">
                            <el-select v-model="row.source_mode" size="small" class="user-input-params__source-mode" @change="commitScriptParams">
                              <el-option v-for="opt in userInputSourceModeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                            <el-select
                              v-if="row.source_mode === 'ref'"
                              v-model="row.ref"
                              filterable
                              allow-create
                              size="small"
                              placeholder="选择引用变量"
                              @change="commitScriptParams"
                            >
                              <el-option v-for="opt in upstreamVarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                            <el-input v-else v-model="row.const_value" size="small" :placeholder="constantPlaceholder(row.type)" @blur="commitScriptParams" />
                          </div>
                        </div>
                        <div class="user-input-params__line user-input-params__line--type">
                          <span class="user-input-params__line-label">类型</span>
                          <div class="user-input-params__type-row">
                            <el-select v-model="row.type" size="small" style="width: 100%" @change="commitScriptParams">
                              <el-option v-for="opt in userInputFieldTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                          </div>
                        </div>
                      </div>
                    </div>
                    <el-button text type="primary" size="small" class="user-input-params__add" @click="addScriptInputRow">＋ 添加字段</el-button>
                  </el-collapse-item>
                  <el-collapse-item title="PYTHON3" name="code">
                    <div class="agent-workflow-insp-field agent-workflow-insp-field--flush">
                      <el-input
                        v-model="scriptCodeDraft"
                        type="textarea"
                        :rows="10"
                        class="agent-workflow-code"
                        placeholder="def main(arg1: str):&#10;    return {&#10;        &quot;result&quot;: arg1,&#10;    }"
                        @blur="commitScriptConfig"
                      />
                    </div>
                    <p class="agent-workflow-script-hint">
                      编写 <code>def main(...)</code>，参数名与输入变量一致；返回 <code>dict</code>，每个输出变量都必须有同名返回键，类型也须一致。数字、布尔、对象和列表常量使用 JSON 格式。未选择引用时，输入使用当前工作流的输入文本。支持 <code>print()</code>；需要下游使用的数据请通过返回字典输出。
                    </p>
                  </el-collapse-item>
                  <el-collapse-item title="输出变量" name="out">
                    <div class="user-input-params">
                      <div v-for="(row, idx) in scriptOutputRows" :key="`sout-${idx}`" class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <span class="user-input-params__line-label">名称</span>
                          <el-input v-model="row.name" size="small" placeholder="返回字段名" @change="commitScriptParams" />
                          <el-button text type="danger" size="small" class="user-input-params__remove" @click="removeScriptOutputRow(idx)">删除</el-button>
                        </div>
                        <div class="user-input-params__line user-input-params__line--type">
                          <span class="user-input-params__line-label">类型</span>
                          <div class="user-input-params__type-row">
                            <el-select v-model="row.type" size="small" style="width: 100%" @change="commitScriptParams">
                              <el-option v-for="opt in userInputFieldTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                          </div>
                        </div>
                      </div>
                    </div>
                    <el-button text type="primary" size="small" class="user-input-params__add" @click="addScriptOutputRow">＋ 添加字段</el-button>
                  </el-collapse-item>
                </el-collapse>
              </template>

              <template v-else-if="inspectorKind === 'agent'">
                <div class="wf-insp-field wf-insp-field--switch-row">
                  <span class="wf-insp-field__label">SSE 输出执行进度</span>
                  <el-switch v-model="agentSseOutputThoughts" @change="commitAgentSseConfig" />
                </div>
                <p class="wf-insp-field__hint">控制子工作流执行进度和调试事件的透传。</p>
                <div class="wf-insp-field wf-insp-field--switch-row">
                  <span class="wf-insp-field__label">SSE 展示实验室结果</span>
                  <el-switch v-model="agentSseOutputResults" @change="commitAgentSseConfig" />
                </div>
                <p class="wf-insp-field__hint">控制该子工作流内实验室的总结、SQL、表格和图表。中间子工作流关闭，最终子工作流开启；子工作流内部的节点开关同时生效。</p>
                <div class="wf-picker-block">
                  <div v-if="agentDraft.target_app_id" class="wf-picker-summary">
                    <div class="wf-picker-summary__main">
                      <div class="wf-picker-summary__title">{{ agentPickedLabel }}</div>
                      <div class="wf-picker-summary__sub">{{ agentPickedVersionLabel }}</div>
                    </div>
                    <div class="wf-picker-summary__ops">
                      <el-button text type="primary" size="small" @click="openAgentPickerDialog">更换</el-button>
                      <el-button text type="danger" size="small" @click="clearAgentSelection">清空</el-button>
                    </div>
                    <div class="wf-picker-summary__version">
                      <el-button size="small" class="wf-picker-summary__version-btn" @click="openAgentVersionDialog">
                        选择版本
                      </el-button>
                    </div>
                  </div>
                  <el-button v-else type="primary" plain class="wf-picker-add" @click="openAgentPickerDialog">
                    <el-icon><Plus /></el-icon>
                    ＋ 添加工作流
                  </el-button>
                </div>
                <el-collapse v-model="agentCollapse" class="agent-workflow-userinput-collapse">
                  <el-collapse-item title="入参" name="in">
                    <div class="user-input-params user-input-params--agent">
                      <div class="user-input-params__header">
                        <span class="user-input-params__line-label">名称</span>
                        <span class="user-input-params__line-label">来源</span>
                        <span class="user-input-params__line-label">类型</span>
                        <span class="user-input-params__line-label">必填</span>
                        <span class="user-input-params__line-label">默认值</span>
                        <span class="user-input-params__line-label" style="width:40px"></span>
                      </div>
                      <div v-for="(row, idx) in agentInputRows" :key="`ain-${idx}`" class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <el-input v-model="row.target_field" size="small" placeholder="目标字段名" @change="commitAgentMappings" />
                        </div>
                        <div class="user-input-params__line user-input-params__line--source">
                          <div class="user-input-params__source-pair">
                            <el-select v-model="row.source_mode" size="small" class="user-input-params__source-mode" @change="commitAgentMappings">
                              <el-option v-for="opt in userInputSourceModeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                            <el-select
                              v-if="row.source_mode === 'ref'"
                              v-model="row.source_ref"
                              filterable
                              allow-create
                              size="small"
                              placeholder="选择引用变量"
                              @change="commitAgentMappings"
                            >
                              <el-option v-for="opt in upstreamVarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                            <el-input v-else v-model="row.const_value" size="small" placeholder="常量值" @blur="commitAgentMappings" />
                          </div>
                        </div>
                        <div class="user-input-params__line">
                          <span class="param-type">{{ row.param_type || 'STRING' }}</span>
                        </div>
                        <div class="user-input-params__line">
                          <el-tag :type="row.required ? 'danger' : 'info'" size="small">{{ row.required ? '是' : '否' }}</el-tag>
                        </div>
                        <div class="user-input-params__line">
                          <span class="param-default">{{ row.default_value ?? '-' }}</span>
                        </div>
                        <div class="user-input-params__line user-input-params__line--action">
                          <el-button text type="danger" size="small" class="user-input-params__remove" @click="removeAgentInputRow(idx)">删除</el-button>
                        </div>
                      </div>
                    </div>
                    <el-button text type="primary" size="small" class="user-input-params__add" @click="addAgentInputRow">＋ 添加字段</el-button>
                  </el-collapse-item>
                  <el-collapse-item title="返回参数" name="out">
                    <div class="user-input-params user-input-params--agent user-input-params--output">
                      <div class="user-input-params__header">
                        <span class="user-input-params__line-label">名称</span>
                        <span class="user-input-params__line-label">类型</span>
                        <span class="user-input-params__line-label">来源字段</span>
                      </div>
                      <div v-for="(row, idx) in agentOutputRows" :key="`aout-${idx}`" class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <el-input v-model="row.target_var" size="small" placeholder="本节点返回名称" @change="commitAgentMappings" />
                        </div>
                        <div class="user-input-params__line">
                          <span class="param-type">{{ row.param_type || 'STRING' }}</span>
                        </div>
                        <div class="user-input-params__line">
                          <el-input v-model="row.source_field" size="small" placeholder="子工作流返回字段，如 content" @change="commitAgentMappings" />
                          <el-button text type="danger" size="small" @click="removeAgentOutputRow(idx)">删除</el-button>
                        </div>
                      </div>
                    </div>
                    <el-button text type="primary" size="small" @click="addAgentOutputRow">＋ 添加返回字段</el-button>
                    <p class="agent-workflow-script-hint">不配置映射时返回 output / content；来源字段填写子工作流的输出字段或“节点名称.字段”。</p>
                  </el-collapse-item>
                </el-collapse>
              </template>

              <template v-else-if="inspectorKind === 'lab'">
                <div class="wf-insp-field wf-insp-field--switch-row">
                  <span class="wf-insp-field__label">SSE 输出执行进度</span>
                  <el-switch v-model="labSseOutputThoughts" @change="commitLabConfig" />
                </div>
                <p class="wf-insp-field__hint">控制实验室执行进度和调试事件的透传。</p>
                <div class="wf-insp-field wf-insp-field--switch-row">
                  <span class="wf-insp-field__label">SSE 展示实验室结果</span>
                  <el-switch v-model="labSseOutputResults" @change="commitLabConfig" />
                </div>
                <p class="wf-insp-field__hint">展示该实验室已启用的总结、SQL、表格和图表。中间实验室关闭，最终实验室开启；总结和图表是否生成沿用实验室设置。</p>
                <div class="wf-picker-block">
                  <div v-if="labDraft.project_id" class="wf-picker-summary">
                    <div class="wf-picker-summary__main">
                      <div class="wf-picker-summary__title">{{ labPickedLabel }}</div>
                      <div class="wf-picker-summary__sub">{{ labPickedDescription || '—' }}</div>
                    </div>
                    <div class="wf-picker-summary__ops">
                      <el-button text type="primary" size="small" @click="openLabPickerDialog">更换</el-button>
                      <el-button text type="danger" size="small" @click="clearLabSelection">清空</el-button>
                    </div>
                  </div>
                  <el-button v-else type="primary" plain class="wf-picker-add" @click="openLabPickerDialog">
                    <el-icon><Plus /></el-icon>
                    ＋ 添加实验室
                  </el-button>
                </div>
                <el-collapse v-model="labCollapse" class="agent-workflow-userinput-collapse">
                  <el-collapse-item title="入参" name="in">
                    <p class="agent-workflow-script-hint">content（query）可选；未传值、空字符串或纯空白时跳过实验室调用，返回空的 summary、sql、trace_id，error 为 null。</p>
                    <div class="user-input-params">
                      <div class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <span class="user-input-params__line-label">content</span>
                          <div style="flex: 1; min-width: 0">
                            <el-radio-group v-model="labContentMode" size="small" @change="commitLabConfig" style="width: 100%">
                              <el-radio-button label="ref">引用</el-radio-button>
                              <el-radio-button label="const">常量</el-radio-button>
                            </el-radio-group>
                            <el-select
                              v-if="labContentMode === 'ref'"
                              v-model="labContentRef"
                              filterable
                              allow-create
                              size="small"
                              placeholder="选择引用 content 变量"
                              @change="commitLabConfig"
                              style="width: 100%; margin-top: 8px"
                            >
                              <el-option
                                v-for="opt in upstreamVarOptions"
                                :key="opt.value"
                                :label="opt.label"
                                :value="opt.value"
                              />
                            </el-select>
                            <el-input
                              v-else
                              v-model="labContentConstText"
                              size="small"
                              type="textarea"
                              :rows="2"
                              placeholder="请输入 content（可选，留空跳过调用）"
                              @blur="commitLabConfig"
                              style="margin-top: 8px"
                            />
                          </div>
                        </div>
                      </div>

                      <div class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <span class="user-input-params__line-label">features</span>
                          <div class="user-input-params__line-note">支持常量/引用（平铺字段，无嵌套）</div>
                        </div>
                        <div class="user-input-params__line user-input-params__line--source">
                          <span class="user-input-params__line-label" style="width: 42px">值</span>
                          <div class="lab-features-editor-wrap" style="flex: 1">
                            <LabFeaturesTreeEditor
                              :model-value="labFeaturesConstObj"
                              :upstream-var-options="upstreamVarOptions"
                              @update:model-value="onLabFeaturesConstObjUpdate"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  </el-collapse-item>

                  <el-collapse-item title="返回参数" name="out">
                    <el-select
                      v-model="labOutputVars"
                      multiple
                      filterable
                      style="width: 100%"
                      placeholder="选择要导出的返回字段"
                      @change="commitLabConfig"
                    >
                      <el-option label="trace_id" value="trace_id" />
                      <el-option label="summary" value="summary" />
                      <el-option label="sql" value="sql" />
                      <el-option label="error" value="error" />
                    </el-select>
                  </el-collapse-item>
                </el-collapse>
              </template>

              <template v-else-if="inspectorKind === 'atomic'">
                <div class="wf-atomic-panel">
                  <div class="wf-atomic-capability">
                    <span class="wf-atomic-capability__label">能力</span>
                    <el-select
                      v-model="atomicDraft.capability"
                      filterable
                      class="wf-atomic-capability__select"
                      @change="onAtomicCapabilityChange"
                    >
                      <el-option
                        v-for="item in ATOMIC_CAPABILITIES"
                        :key="item.value"
                        :label="item.label"
                        :value="item.value"
                      />
                    </el-select>
                  </div>

                  <div class="wf-atomic-section">
                    <div class="wf-atomic-section__head">
                      <span>常用参数</span>
                    </div>
                    <p class="agent-workflow-script-hint">* 为必填；可选参数留空使用默认值。生成 SQL 的知识库可留空，NER 的查询内容可留空。阈值填 null 表示不设置阈值。</p>
                    <div class="wf-atomic-grid">
                      <div
                        v-for="row in atomicPrimaryRows"
                        :key="`atomic-primary-${row.key}`"
                        class="wf-atomic-row"
                        :class="{ 'wf-atomic-row--wide': row.wide || row.multiline }"
                      >
                        <div class="wf-atomic-row__meta">
                          <span class="wf-atomic-row__key">{{ row.label || row.key }} <span class="wf-atomic-required">{{ row.required ? '*' : '（可选）' }}</span></span>
                          <span class="wf-atomic-row__type">{{ row.type || 'STRING' }}</span>
                        </div>
                        <div class="wf-atomic-row__body">
                          <el-select
                            v-model="row.source_mode"
                            size="small"
                            class="wf-atomic-mode"
                            @change="onAtomicRowModeChange(row)"
                          >
                            <el-option v-for="opt in userInputSourceModeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                          </el-select>
                          <el-select
                            v-if="row.source_mode === 'ref'"
                            v-model="row.source_ref"
                            filterable
                            allow-create
                            size="small"
                            placeholder="选择引用变量"
                            class="wf-atomic-value"
                            @change="commitAtomicConfig"
                          >
                            <el-option v-for="opt in upstreamVarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                          </el-select>
                          <component
                            :is="atomicConstControl(row)"
                            v-else
                            v-model="row.const_value"
                            v-bind="atomicConstProps(row)"
                            class="wf-atomic-value"
                            @change="commitAtomicConfig"
                            @blur="commitAtomicConfig"
                          >
                            <template v-if="row.control === 'knowledgeBase'">
                              <el-option v-for="opt in knowledgeBaseOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </template>
                            <template v-else-if="row.control === 'modelProvider'">
                              <el-option v-for="opt in atomicModelProviderOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </template>
                            <template v-else-if="row.control === 'modelName'">
                              <el-option v-for="opt in atomicModelNameOptions" :key="opt" :label="opt" :value="opt" />
                            </template>
                          </component>
                        </div>
                      </div>
                    </div>
                  </div>

                  <el-collapse v-if="isAtomicGenerateSql" v-model="atomicPromptCollapse" class="wf-atomic-advanced">
                    <el-collapse-item title="生成 SQL 提示词模板" name="prompt">
                      <div class="wf-atomic-prompt">
                        <p class="wf-atomic-prompt__hint">
                          模板支持 <code v-pre>{{query}}</code> 和自定义上下文占位，例如 <code v-pre>{{knowledge}}</code>。
                          未配置的占位会原样保留，不会阻塞执行。
                        </p>
                        <el-input
                          v-model="atomicSystemPrompt"
                          type="textarea"
                          :rows="8"
                          resize="vertical"
                          class="wf-atomic-prompt__textarea"
                          @blur="commitAtomicConfig"
                        />
                        <div class="wf-atomic-context">
                          <div class="wf-atomic-context__head">
                            <span>参数引用</span>
                            <el-button text type="primary" size="small" @click="addAtomicContextRow">添加参数</el-button>
                          </div>
                          <div v-for="(row, idx) in atomicContextRows" :key="`ctx-${idx}`" class="wf-atomic-context__row">
                            <el-input v-model="row.name" size="small" placeholder="参数名，如 knowledge" @blur="commitAtomicConfig" />
                            <el-select v-model="row.source_mode" size="small" @change="commitAtomicConfig">
                              <el-option label="引用" value="ref" />
                              <el-option label="常量" value="const" />
                            </el-select>
                            <el-select
                              v-if="row.source_mode === 'ref'"
                              v-model="row.source_ref"
                              filterable
                              allow-create
                              size="small"
                              placeholder="选择上游变量"
                              @change="commitAtomicConfig"
                            >
                              <el-option v-for="opt in upstreamVarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                            </el-select>
                            <el-input
                              v-else
                              v-model="row.const_value"
                              size="small"
                              placeholder="常量上下文"
                              @blur="commitAtomicConfig"
                            />
                            <el-button text type="danger" size="small" @click="removeAtomicContextRow(idx)">删除</el-button>
                          </div>
                        </div>
                      </div>
                    </el-collapse-item>
                  </el-collapse>

                  <el-collapse v-if="atomicAdvancedRows.length" v-model="atomicAdvancedCollapse" class="wf-atomic-advanced">
                    <el-collapse-item :title="isAtomicGenerateSql ? '模型参数' : '高级参数'" name="advanced">
                      <div class="wf-atomic-compact-grid">
                        <div v-for="row in atomicAdvancedRows" :key="`atomic-adv-${row.key}`" class="wf-atomic-compact">
                          <span class="wf-atomic-compact__label">{{ row.label || row.key }}</span>
                          <el-input
                            v-model="row.const_value"
                            size="small"
                            class="wf-atomic-compact__input"
                            @blur="commitAtomicConfig"
                          />
                        </div>
                      </div>
                    </el-collapse-item>
                  </el-collapse>

                  <div class="wf-atomic-section wf-atomic-section--outputs">
                    <div class="wf-atomic-section__head">
                      <span>输出变量</span>
                    </div>
                    <div class="wf-atomic-output-chips">
                      <el-tag v-for="row in atomicOutputRows" :key="`${atomicDraft.capability}-${row.key}`" effect="plain" disable-transitions>
                        {{ row.key }} · {{ row.type || 'STRING' }}
                      </el-tag>
                    </div>
                  </div>
                </div>
              </template>

              <template v-else-if="inspectorKind === 'externalApi'">
                <div class="agent-workflow-insp-field">
                  <span class="agent-workflow-insp-label">方法</span>
                  <el-select v-model="apiDraft.method" style="width: 100%" @change="commitApiConfig">
                    <el-option label="GET" value="GET" />
                    <el-option label="POST" value="POST" />
                    <el-option label="PUT" value="PUT" />
                    <el-option label="PATCH" value="PATCH" />
                    <el-option label="DELETE" value="DELETE" />
                  </el-select>
                </div>
                <div class="agent-workflow-insp-field">
                  <span class="agent-workflow-insp-label">Base URL</span>
                  <el-input v-model="apiDraft.base_url" @blur="commitApiConfig" />
                </div>
                <div class="agent-workflow-insp-field">
                  <span class="agent-workflow-insp-label">Path</span>
                  <el-input v-model="apiDraft.path" placeholder="/v1/xxx" @blur="commitApiConfig" />
                </div>
                <div class="agent-workflow-insp-field">
                  <span class="agent-workflow-insp-label">超时（秒）</span>
                  <el-input-number v-model="apiDraft.timeout" :min="1" :max="600" @change="commitApiConfig" />
                </div>
                <el-collapse v-model="apiCollapse" class="agent-workflow-userinput-collapse">
                  <el-collapse-item title="请求参数" name="request">
                    <div v-for="section in ['headers', 'query']" :key="section" class="agent-workflow-insp-field">
                      <span class="agent-workflow-insp-label">{{ section === 'headers' ? '请求头 Headers' : '查询参数 Query' }}</span>
                      <div v-for="(row, idx) in apiDraft[section]" :key="idx" class="agent-workflow-insp-rowline">
                        <el-input v-model="row.key" placeholder="字段名" size="small" @change="commitApiConfig" />
                        <el-input v-model="row.value" placeholder="值或 {{节点.字段}}" size="small" @change="commitApiConfig" />
                        <el-button text type="danger" size="small" @click="apiDraft[section].splice(idx, 1); commitApiConfig()">删除</el-button>
                      </div>
                      <el-button text type="primary" size="small" @click="apiDraft[section].push({ key: '', value: '' })">＋ 添加字段</el-button>
                    </div>
                    <div v-if="['POST', 'PUT', 'PATCH'].includes(apiDraft.method)" class="agent-workflow-insp-field">
                      <span class="agent-workflow-insp-label">请求体 Body</span>
                      <el-input v-model="apiDraft.body_template" type="textarea" :rows="5" placeholder='JSON 或文本，支持 {{节点.字段}} 引用' @blur="commitApiConfig" />
                    </div>
                    <p class="agent-workflow-script-hint">Base URL、Path、请求头、查询参数与请求体均支持双花括号变量引用。</p>
                  </el-collapse-item>
                  <el-collapse-item title="返回参数" name="out">
                    <div class="wf-atomic-output-chips">
                      <el-tag type="info">status_code · NUMBER</el-tag>
                      <el-tag type="info">response_body · STRING</el-tag>
                    </div>
                    <p class="agent-workflow-script-hint">固定返回 HTTP 状态码和原始响应正文。下方可通过 JSON Path 提取额外字段（支持 $.data[0].answer）。</p>
                    <div class="user-input-params">
                      <div v-for="(row, idx) in apiOutputRows" :key="`apiout-${idx}`" class="user-input-params__row">
                        <div class="user-input-params__line user-input-params__line--name">
                          <span class="user-input-params__line-label">名称</span>
                          <el-input v-model="row.name" size="small" placeholder="字段名" @change="commitApiOutputVars" />
                          <el-button text type="danger" size="small" class="user-input-params__remove" @click="removeApiOutputRow(idx)">删除</el-button>
                        </div>
                        <div class="user-input-params__line user-input-params__line--source">
                          <span class="user-input-params__line-label">来源</span>
                          <el-input v-model="row.json_path" size="small" placeholder="JSON Path，如 $.data.answer" @blur="commitApiOutputVars" />
                        </div>
                      </div>
                    </div>
                    <el-button text type="primary" size="small" class="user-input-params__add" @click="addApiOutputRow">＋ 添加字段</el-button>
                  </el-collapse-item>
                </el-collapse>
              </template>

              <template v-else-if="inspectorKind === 'selector'">
                <div class="wf-insp-panel wf-insp-panel--selector">
                  <div class="wf-insp-callout">
                    <span class="wf-insp-callout__icon" aria-hidden="true">
                      <el-icon><InfoFilled /></el-icon>
                    </span>
                    <div class="wf-insp-callout__body">
                      <span class="wf-insp-callout__title">匹配规则</span>
                      <p class="wf-insp-callout__text">
                        自上而下依次匹配，命中第一个分支即走该出口；同一分支可选择「且 / 或」。请从画布节点右侧 IF / ELIF / ELSE 各行对应的圆点连线到下游。
                      </p>
                    </div>
                  </div>

                  <div v-for="(cRow, ci) in selectorCaseRows" :key="cRow.id" class="wf-insp-branch-card">
                    <div class="wf-insp-branch-card__head">
                      <div class="wf-insp-branch-card__title-block">
                        <span class="wf-insp-branch-pill">{{ ci === 0 ? 'IF' : 'ELIF' }}</span>
                        <span class="wf-inp-branch-name">{{ ci === 0 ? '分支 1' : `分支 ${ci + 1}` }}</span>
                      </div>
                      <el-button
                        v-if="selectorCaseRows.length > 1"
                        text
                        type="danger"
                        size="small"
                        class="wf-inp-text-danger"
                        @click="removeSelectorCase(ci)"
                      >
                        删除分支
                      </el-button>
                    </div>
                    <div class="wf-inp-conds-header">
                      <span class="wf-inp-conds-relation-label">条件关系</span>
                      <el-radio-group v-model="cRow.relation" size="small" @change="commitSelectorConfig">
                        <el-radio-button label="AND">且</el-radio-button>
                        <el-radio-button label="OR">或</el-radio-button>
                      </el-radio-group>
                    </div>
                    <div class="wf-inp-conds">
                      <div class="wf-inp-conds__legend" aria-hidden="true">
                        <span>变量</span>
                        <span>运算符</span>
                        <span>比较值</span>
                        <span class="wf-inp-conds__legend-actions" />
                      </div>
                      <div
                        v-for="(cond, qi) in cRow.conditions"
                        :key="qi"
                        class="wf-inp-conds__row"
                      >
                        <el-select
                          v-model="cond.ref"
                          filterable
                          allow-create
                          size="small"
                          class="wf-inp-conds__cell wf-inp-conds__ref"
                          placeholder="如 LLM.text"
                          @change="commitSelectorConfig"
                        >
                          <el-option v-for="opt in upstreamVarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                        </el-select>
                        <el-select
                          v-model="cond.op"
                          size="small"
                          class="wf-inp-conds__cell wf-inp-conds__op"
                          @change="commitSelectorConfig"
                        >
                          <el-option v-for="o in SELECTOR_OPERATORS" :key="o.value" :label="o.label" :value="o.value" />
                        </el-select>
                        <div class="wf-inp-conds__cell wf-inp-conds__val-wrap">
                          <el-input
                            v-if="!['empty', 'not_empty'].includes(cond.op)"
                            v-model="cond.value"
                            size="small"
                            placeholder="比较值"
                            @blur="commitSelectorConfig"
                          />
                          <span v-else class="wf-inp-conds__na">无需填写</span>
                        </div>
                        <el-button
                          text
                          type="danger"
                          size="small"
                          class="wf-inp-conds__rm"
                          @click="removeSelectorCondition(ci, qi)"
                        >
                          移除
                        </el-button>
                      </div>
                    </div>
                    <el-button text type="primary" size="small" class="wf-inp-add-cond" @click="addSelectorCondition(ci)">
                      ＋ 添加条件
                    </el-button>
                  </div>

                  <el-button class="wf-inp-add-branch" type="primary" plain @click="addSelectorCase">
                    ＋ 添加 ELIF 分支
                  </el-button>

                  <div class="wf-inp-else-card">
                    <div class="wf-inp-else-card__head">
                      <span class="wf-inp-branch-pill wf-inp-branch-pill--else">ELSE</span>
                      <span class="wf-inp-else-card__sub">默认出口</span>
                    </div>
                    <p class="wf-inp-else-card__desc">
                      当以上条件均不满足时走此路；在画布最下方 ELSE 行右侧圆点连接下游节点。
                    </p>
                  </div>
                </div>
              </template>

              <div v-else-if="inspectorKind && !['start', 'userInput', 'output', 'llm', 'script', 'selector', 'agent', 'lab', 'atomic', 'externalApi'].includes(inspectorKind)" class="agent-workflow-inspector__placeholder">
                <p>节点类型：<strong>{{ inspectorKindLabel }}</strong></p>
              </div>
          </div>
          </fieldset>
        </aside>
    </div>

    <el-dialog
      v-model="agentPickerVisible"
      width="920px"
      destroy-on-close
      class="wf-agent-picker-dialog"
    >
      <template #title>
        <div class="wf-dialog-title">
          <span>选择工作流</span>
          <el-tag type="info" size="small">工作流</el-tag>
        </div>
      </template>

      <div class="wf-dialog-search">
        <el-input
          v-model="agentPickerKeyword"
          placeholder="请输入工作流名称/描述"
          clearable
          @keyup.enter="refreshAgentApps"
        />
        <el-button size="small" @click="refreshAgentApps">搜索</el-button>
      </div>

      <div v-if="agentPickerLoading" class="wf-dialog-loading">加载中…</div>

      <div v-else class="wf-dialog-grid wf-dialog-grid--agents">
        <div
          v-for="a in agentPickerApps"
          :key="a.id"
          class="wf-pick-card"
          :class="{ 'is-active': a.id === agentDraft.target_app_id }"
          role="button"
          tabindex="0"
          @click="pickAgentApp(a)"
        >
          <div class="wf-pick-card__left">
            <div class="wf-pick-card__icon">{{ a.icon || '*' }}</div>
          </div>
          <div class="wf-pick-card__right">
            <div class="wf-pick-card__name">
              {{ a.name }}
            </div>
            <div class="wf-pick-card__desc">
              {{ a.description || '—' }}
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <span class="wf-dialog-footer-note">选择后将继续选择版本。</span>
        <el-button @click="agentPickerVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="agentVersionDialogVisible"
      width="620px"
      destroy-on-close
      class="wf-agent-version-dialog"
    >
      <template #title>
        <div class="wf-dialog-title">
          <span>选择版本</span>
          <el-tag type="info" size="small">工作流</el-tag>
        </div>
      </template>

      <div class="wf-version-body">
        <el-select
          v-model="agentVersionSelectValue"
          filterable
          placeholder="请选择版本"
          style="width: 100%"
        >
          <el-option
            v-for="v in agentVersionOptions"
            :key="v.id"
            :label="formatAgentVersionLabel(v)"
            :value="v.id"
          />
          <el-option
            :value="DEFAULT_OUTPUT_SENTINEL"
            label="选择默认当前版本"
          />
        </el-select>
      </div>

      <template #footer>
        <el-button @click="cancelAgentVersion">取消</el-button>
        <el-button type="primary" @click="confirmAgentVersion">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="labPickerVisible"
      width="920px"
      destroy-on-close
      class="wf-lab-picker-dialog"
    >
      <template #title>
        <div class="wf-dialog-title">
          <span>选择实验室</span>
          <el-tag type="success" size="small">实验室</el-tag>
        </div>
      </template>

      <div class="wf-dialog-search">
        <el-input
          v-model="labPickerKeyword"
          placeholder="请输入实验室名称/描述"
          clearable
          @keyup.enter="refreshLabProjects"
        />
        <el-button size="small" @click="refreshLabProjects">搜索</el-button>
      </div>

      <div v-if="labPickerLoading" class="wf-dialog-loading">加载中…</div>

      <div v-else class="wf-dialog-grid wf-dialog-grid--labs">
        <div
          v-for="p in labPickerFilteredProjects"
          :key="p.id"
          class="wf-pick-card"
          :class="{ 'is-active': p.id === labDraft.project_id }"
          role="button"
          tabindex="0"
          @click="pickLabProject(p)"
        >
          <div class="wf-pick-card__left">
            <div class="wf-pick-card__icon wf-pick-card__icon--lab">LAB</div>
          </div>
          <div class="wf-pick-card__right">
            <div class="wf-pick-card__name">
              {{ p.name }}
            </div>
            <div class="wf-pick-card__desc">
              {{ p.description || '—' }}
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <span class="wf-dialog-footer-note">选择后将立即应用到当前节点。</span>
        <el-button @click="labPickerVisible = false">关闭</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { computed, markRaw, nextTick, onMounted, onUnmounted, provide, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { VueFlow, addEdge, useNodesInitialized, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft,
  ArrowDown,
  Plus,
  VideoPlay,
  Close,
  Cpu,
  Document,
  Avatar,
  MagicStick,
  Link,
  Flag,
  House,
  Promotion,
  Setting,
  RefreshLeft,
  RefreshRight,
  Monitor,
  Share,
  InfoFilled,
  SetUp
} from '@element-plus/icons-vue'
import agentAppApi from '@/api/agentApp'
import { getModelProviders } from '@/api/modelProvider'
import { getAutobiProject, listAutobiProjects } from '@/api/autobi'
import knowledgeBaseApi from '@/api/knowledgeBase'
import WfCardNode from './WfCardNode.vue'
import WfSelectorNode from './WfSelectorNode.vue'
import WfPlusEdge from './WfPlusEdge.vue'
import LabFeaturesTreeEditor from './LabFeaturesTreeEditor.vue'
import { ATOMIC_CAPABILITIES, buildAtomicInputRows } from './atomicCapabilities.js'
import { LAB_OUTPUT_FIELDS, LLM_OUTPUT_FIELDS, constantPlaceholder, formatWorkflowValue, nodeOutputOptions, nodeConfigurationIssues, renameNodeReferences } from './workflowContracts.js'
import { workflowSnapshot, sameWorkflow, mergeWorkflows } from './workflowPersistence.js'

const props = defineProps({
  appId: { type: String, required: true },
  versionId: { type: String, required: true }
})

const route = useRoute()
const router = useRouter()
const { fitView, dimensions: viewportDimensions } = useVueFlow()
const nodesInitialized = useNodesInitialized()
const pendingViewportFit = ref(null)
let viewportDisposed = false

const loading = ref(true)
const app = ref(null)

// Async graphs arrive after Vue Flow's initial render. Fit only once real bounds
// and the inspector-adjusted viewport are available, without resetting user pans.
function requestViewportFit(nodeIds = null) {
  pendingViewportFit.value = { nodeIds }
}
watch(
  () => [loading.value, nodesInitialized.value, viewportDimensions.value.width, viewportDimensions.value.height, pendingViewportFit.value],
  async () => {
    const request = pendingViewportFit.value
    if (!request || loading.value || !nodesInitialized.value || !viewportDimensions.value.width) return
    await nextTick()
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    if (viewportDisposed || request !== pendingViewportFit.value || loading.value || !nodesInitialized.value) return
    const fitted = await fitView({
      ...(request.nodeIds ? { nodes: request.nodeIds } : {}),
      padding: 0.2, minZoom: 0.1, maxZoom: 1, duration: 200
    })
    if (fitted && request === pendingViewportFit.value) pendingViewportFit.value = null
  },
  { flush: 'post' }
)

/**
 * 仅「编排中」版本可编辑画布；已发布/已上线强制只读（避免手改 URL）。
 * 加载完成前只读；显式 ?readonly=1 时「编排中」也可只读预览。
 */
const workflowReadonly = computed(() => {
  if (loading.value) return true
  const vid = Number(props.versionId)
  const v = app.value?.versions?.find((x) => x.id === vid)
  if (!v) return true
  if (v.status !== 'designing') return true
  const q = route.query.readonly
  return q === '1' || q === 'true'
})

const nodeTypes = {
  wfCard: markRaw(WfCardNode),
  wfSelector: markRaw(WfSelectorNode)
}

const edgeTypes = {
  wfPlus: markRaw(WfPlusEdge)
}

const defaultEdgeOptions = { type: 'wfPlus' }

const PALETTE = [
  { kind: 'llm', label: 'LLM' },
  { kind: 'script', label: '脚本任务' },
  { kind: 'selector', label: '选择器' },
  { kind: 'agent', label: '工作流' },
  { kind: 'lab', label: '实验室' },
  { kind: 'atomic', label: '原子能力' },
  { kind: 'externalApi', label: '外部 API' },
  { kind: 'output', label: '输出' }
]

const KIND_LABEL = {
  start: '开始',
  userInput: '用户输入',
  llm: 'LLM',
  script: '脚本任务',
  selector: '选择器',
  agent: '工作流',
  lab: '实验室',
  atomic: '原子能力',
  externalApi: '外部 API',
  output: '输出'
}


const DEFAULT_GENERATE_SQL_PROMPT =
  '你是 Text-to-SQL 助手。请根据用户问题和上下文生成一条 {{database_type}} 只读 SELECT 查询。\n' +
  '要求：\n' +
  '1. 只输出 SQL，不要 Markdown、解释或代码围栏。\n' +
  '2. 禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE 等写操作。\n' +
  '3. 表名、字段名必须来自上下文；无法确认时生成保守查询或返回 SELECT NULL AS result。\n' +
  '4. 优先参考知识信息与 SQL 样例。\n\n' +
  '【知识信息】\n{{knowledge}}\n\n' +
  '【SQL样例】\n{{examples}}\n\n' +
  '【用户问题】\n{{query}}\n\n' +
  'SQL:'

const DEFAULT_NODES = [
  {
    id: 'wf-start',
    type: 'wfCard',
    position: { x: 64, y: 140 },
    data: { kind: 'start', label: '开始' }
  },
  {
    id: 'wf-user-input',
    type: 'wfCard',
    position: { x: 460, y: 140 },
    data: {
      kind: 'userInput',
      label: '用户输入',
      fields: [
        {
          variable: 'input',
          display: 'input',
          type: 'string',
          required: true,
          hidden: false,
          default: '',
          description: '',
          source_mode: 'ref',
          source_ref: ['input', 'input'],
          maxLength: null
        }
      ]
    }
  }
]

const DEFAULT_EDGES = [
  {
    id: 'e-start-user',
    source: 'wf-start',
    target: 'wf-user-input',
    type: 'wfPlus'
  }
]

const nodes = ref(JSON.parse(JSON.stringify(DEFAULT_NODES)))
const edges = ref(JSON.parse(JSON.stringify(DEFAULT_EDGES)))

const paletteForMenu = computed(() => PALETTE)

const selectedNodeId = ref(null)
const inspectorReloadKey = ref(0)

const modelProviders = ref([])
const arrangingLayout = ref(false)

const inspectorLabelDraft = ref('')
const userInputCollapse = ref(['params'])
const userInputFieldRows = ref([])
const llmInputParamRows = ref([])
const outputTemplateDraft = ref('')
const outputContentRows = ref([
  { output_format: 'text', source_ref: '', source_mode: 'ref', const_value: '' }
])
const outputMetadataRows = ref([
  { name: '', source_ref: '', source_mode: 'ref', type: 'STRING', const_value: '' }
])
const outputCollapse = ref(['content', 'metadata', 'advanced'])
const scriptCodeDraft = ref('')
const scriptCollapse = ref(['in', 'code', 'out'])
const llmCollapse = ref(['model', 'prompt'])
const scriptInputRows = ref([])
const scriptOutputRows = ref([])
const llmStopWords = ref([])
const llmStopWordsText = ref('')
const agentCollapse = ref(['in', 'out'])
const agentInputRows = ref([])
const agentOutputRows = ref([])
const agentSseOutputThoughts = ref(true)
const agentSseOutputResults = ref(true)
const atomicCollapse = ref(['in', 'out'])
const atomicAdvancedCollapse = ref([])
const atomicPromptCollapse = ref(['prompt'])
const atomicInputRows = ref([])
const atomicOutputRows = computed(() => normalizeAtomicOutputRows(atomicDraft.capability))
const atomicContextRows = ref([])
const atomicSystemPrompt = ref('')
const knowledgeBaseOptions = ref([])
const apiCollapse = ref(['request', 'out'])
const apiOutputRows = ref([])
const labContentMode = ref('const')
const labContentRef = ref('')
const labContentConstText = ref('')
const labCollapse = ref(['in', 'out'])
const labSseOutputThoughts = ref(true)
const labSseOutputResults = ref(true)
const selectorCaseRows = ref([])
const SELECTOR_OPERATORS = [
  { value: 'contains', label: '包含' },
  { value: 'not_contains', label: '不包含' },
  { value: 'starts_with', label: '开始是' },
  { value: 'ends_with', label: '结束是' },
  { value: 'eq', label: '是' },
  { value: 'ne', label: '不是' },
  { value: 'empty', label: '为空' },
  { value: 'not_empty', label: '不为空' }
]
const labFeaturesConstObj = ref({})
const labOutputVars = ref([...LAB_OUTPUT_FIELDS])

const DEFAULT_OUTPUT_SENTINEL = '__DEFAULT_OUTPUT__'

// ===== 工作流 / 实验室选择对话框状态 =====
const agentPickerVisible = ref(false)
const agentPickerKeyword = ref('')
const agentPickerLoading = ref(false)
const agentPickerApps = ref([])
const agentVersionDialogVisible = ref(false)
const agentVersionOptions = ref([])
const agentVersionSelectValue = ref(DEFAULT_OUTPUT_SENTINEL)
const agentVersionBackup = ref({ appId: null, versionId: null })
const agentPickedDetail = ref(null)

const labPickerVisible = ref(false)
const labPickerKeyword = ref('')
const labPickerLoading = ref(false)
const labPickerProjects = ref([])
const labPickedProject = ref(null)

let agentDetailFetchSeq = 0
let labDetailFetchSeq = 0

const llmDraft = reactive({
  provider_id: null,
  model_name: '',
  temperature: 0.7,
  max_tokens: 2000,
  top_p: 0.9,
  context_vars: [],
  system_prompt: '',
  use_user_prompt_template: false,
  user_prompt: '',
  param_bindings: {},
  input_params: [],
  stop_words: [],
  output_params: []
})

const LLM_NAMED_SLOT_RE = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g

const llmNamedSlotKeys = computed(() => {
  const seen = new Set()
  const keys = []
  const scan = (text) => {
    if (text == null || text === '') return
    const s = String(text)
    const local = new RegExp(LLM_NAMED_SLOT_RE.source, 'g')
    let m
    while ((m = local.exec(s)) !== null) {
      const k = m[1]
      if (!seen.has(k)) {
        seen.add(k)
        keys.push(k)
      }
    }
  }
  scan(llmDraft.system_prompt)
  if (llmDraft.use_user_prompt_template) scan(llmDraft.user_prompt)
  return keys
})

watch(
  llmNamedSlotKeys,
  (slotKeys) => {
    for (const k of slotKeys) {
      if (!llmDraft.param_bindings[k]) {
        llmDraft.param_bindings[k] = { source_mode: 'ref', ref: '', const_value: '' }
      }
    }
  },
  { immediate: true, flush: 'sync' }
)
const agentDraft = reactive({ target_app_id: null, target_version_id: null })
const labDraft = reactive({ project_id: null })
const atomicDraft = reactive({ capability: 'elasticsearch-value-retriever' })
const apiDraft = reactive({ method: 'GET', base_url: '', path: '', timeout: 60, headers: [], query: [], body_template: '' })

/** 画布状态快照：最多保留 10 步，拖拽结束与各操作后自动入栈 */
const MAX_HISTORY = 10
const history = ref([])
const historyIndex = ref(-1)
const isApplyingHistory = ref(false)

/** 与后端乐观锁对齐；加载完成后赋值 */
const workflowRev = ref(0)
const suppressSave = ref(true)
const savingWorkflow = ref(false)
const hasUnsavedChanges = ref(false)
const lastSavedSnapshot = ref(null)
const autosavePaused = ref(false)
let saveTimer = null
/** features 树每次 emit 会高频触发，防抖后再 commit，避免撤销栈被逐字刷屏 */
let labFeaturesCommitTimer = null
const SAVE_DEBOUNCE_MS = 500

function cloneState() {
  return workflowSnapshot({ nodes: nodes.value, edges: edges.value })
}

function normalizeEdgeList(edgeList) {
  return (edgeList || []).map((e, idx) => ({
    ...e,
    id: e?.id || `e-legacy-${idx}-${e?.source || 's'}-${e?.target || 't'}`,
    type: 'wfPlus'
  }))
}

function restoreState(s) {
  nodes.value = JSON.parse(JSON.stringify(s.nodes))
  const raw = JSON.parse(JSON.stringify(s.edges || []))
  edges.value = normalizeEdgeList(raw)
}

function pushHistory() {
  if (workflowReadonly.value) return
  if (isApplyingHistory.value) return
  edges.value = applyBranchEdgeColors(nodes.value, edges.value)
  const snap = cloneState()
  const last = history.value[historyIndex.value]
  if (last && sameWorkflow(last, snap)) return
  history.value = history.value.slice(0, historyIndex.value + 1)
  history.value.push(snap)
  if (history.value.length > MAX_HISTORY) {
    history.value.shift()
  }
  historyIndex.value = history.value.length - 1
  hasUnsavedChanges.value = true
  scheduleDebouncedSave()
}

function syncSelectionAfterHistory() {
  inspectorReloadKey.value += 1
  if (selectedNodeId.value && !nodes.value.some((n) => n.id === selectedNodeId.value)) {
    selectedNodeId.value = null
  }
}

function undo() {
  if (historyIndex.value <= 0) return
  historyIndex.value--
  isApplyingHistory.value = true
  restoreState(history.value[historyIndex.value])
  nextTick(() => {
    isApplyingHistory.value = false
    syncSelectionAfterHistory()
    hasUnsavedChanges.value = true
    scheduleDebouncedSave()
  })
}

function redo() {
  if (historyIndex.value >= history.value.length - 1) return
  historyIndex.value++
  isApplyingHistory.value = true
  restoreState(history.value[historyIndex.value])
  nextTick(() => {
    isApplyingHistory.value = false
    syncSelectionAfterHistory()
    hasUnsavedChanges.value = true
    scheduleDebouncedSave()
  })
}

function initHistory() {
  history.value = [cloneState()]
  historyIndex.value = 0
}

const canUndo = computed(() => historyIndex.value > 0)
const canRedo = computed(() => history.value.length > 0 && historyIndex.value < history.value.length - 1)

const BRANCH_COLORS = ['#5b7cfa', '#16a34a', '#f59e0b', '#ec4899', '#14b8a6', '#a855f7']

function applyBranchEdgeColors(nodeList, edgeList) {
  const ids = new Set((nodeList || []).map((n) => n.id))
  const outEdges = (edgeList || []).map((e) => ({ ...e }))
  const children = new Map()
  for (const e of outEdges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue
    if (!children.has(e.source)) children.set(e.source, [])
    children.get(e.source).push(e.target)
  }
  const nodesById = Object.fromEntries((nodeList || []).map((n) => [n.id, n]))
  const start = (nodeList || []).find((n) => n.data?.kind === 'start')
  if (!start) return outEdges

  let splitNodeId = start.id
  const startChildren = children.get(start.id) || []
  if (startChildren.length === 1) {
    const only = nodesById[startChildren[0]]
    if (only?.data?.kind === 'userInput') splitNodeId = only.id
  }
  const roots = children.get(splitNodeId) || []
  if (!roots.length) return outEdges

  const mark = new Map()
  for (let bi = 0; bi < roots.length; bi += 1) {
    const stack = [roots[bi]]
    const seen = new Set()
    while (stack.length) {
      const u = stack.pop()
      if (seen.has(u)) continue
      seen.add(u)
      if (!mark.has(u)) mark.set(u, new Set())
      mark.get(u).add(bi)
      for (const v of children.get(u) || []) stack.push(v)
    }
  }

  return outEdges.map((e) => {
    let idx = -1
    if (e.source === splitNodeId) idx = roots.indexOf(e.target)
    else {
      const s = mark.get(e.source)
      if (s && s.size === 1) idx = [...s][0]
    }
    const stroke = idx >= 0 ? BRANCH_COLORS[idx % BRANCH_COLORS.length] : '#c6cbd4'
    return { ...e, style: { ...(e.style || {}), stroke, strokeWidth: 2 } }
  })
}

function computeBranchMembership(nodeList, edgeList) {
  const ids = new Set((nodeList || []).map((n) => n.id))
  const children = new Map()
  for (const e of edgeList || []) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue
    if (!children.has(e.source)) children.set(e.source, [])
    children.get(e.source).push(e.target)
  }
  const nodesById = Object.fromEntries((nodeList || []).map((n) => [n.id, n]))
  const start = (nodeList || []).find((n) => n.data?.kind === 'start')
  if (!start) return { roots: [], branchSetByNode: new Map() }

  let splitNodeId = start.id
  const startChildren = children.get(start.id) || []
  if (startChildren.length === 1) {
    const only = nodesById[startChildren[0]]
    if (only?.data?.kind === 'userInput') splitNodeId = only.id
  }
  const roots = children.get(splitNodeId) || []
  const branchSetByNode = new Map()
  for (let bi = 0; bi < roots.length; bi += 1) {
    const stack = [roots[bi]]
    const seen = new Set()
    while (stack.length) {
      const u = stack.pop()
      if (seen.has(u)) continue
      seen.add(u)
      if (!branchSetByNode.has(u)) branchSetByNode.set(u, new Set())
      branchSetByNode.get(u).add(bi)
      for (const v of children.get(u) || []) stack.push(v)
    }
  }
  return { roots, branchSetByNode }
}

function computeLayoutLevels(nodeList, edgeList) {
  const ids = nodeList.map((n) => n.id).filter(Boolean)
  const idSet = new Set(ids)
  const indeg = {}
  const parents = {}
  const children = {}
  for (const id of ids) {
    indeg[id] = 0
    parents[id] = []
    children[id] = []
  }
  for (const e of edgeList || []) {
    const s = e?.source
    const t = e?.target
    if (!idSet.has(s) || !idSet.has(t)) continue
    indeg[t] += 1
    parents[t].push(s)
    children[s].push(t)
  }

  const yMap = Object.fromEntries(nodeList.map((n) => [n.id, n.position?.y ?? 0]))
  let q = ids.filter((id) => indeg[id] === 0).sort((a, b) => (yMap[a] - yMap[b]) || String(a).localeCompare(String(b)))
  const topo = []
  while (q.length) {
    const u = q.shift()
    topo.push(u)
    for (const v of children[u]) {
      indeg[v] -= 1
      if (indeg[v] === 0) q.push(v)
    }
    q.sort((a, b) => (yMap[a] - yMap[b]) || String(a).localeCompare(String(b)))
  }
  if (topo.length !== ids.length) return ids.map((id) => [id])

  const levelOf = {}
  for (const id of topo) {
    const ps = parents[id]
    levelOf[id] = ps.length ? Math.max(...ps.map((p) => levelOf[p] ?? 0)) + 1 : 0
  }
  const maxLv = Math.max(...Object.values(levelOf))
  const levels = Array.from({ length: maxLv + 1 }, () => [])
  for (const id of topo) levels[levelOf[id]].push(id)

  const orderPos = {}
  levels[0].forEach((id, i) => { orderPos[id] = i })
  for (let lv = 1; lv < levels.length; lv += 1) {
    levels[lv].sort((a, b) => {
      const ap = parents[a] || []
      const bp = parents[b] || []
      const ac = ap.length ? ap.reduce((s, p) => s + (orderPos[p] ?? 0), 0) / ap.length : (yMap[a] ?? 0)
      const bc = bp.length ? bp.reduce((s, p) => s + (orderPos[p] ?? 0), 0) / bp.length : (yMap[b] ?? 0)
      return ac - bc
    })
    levels[lv].forEach((id, i) => { orderPos[id] = i })
  }
  return levels
}

async function arrangeWorkflowLayout() {
  if (workflowReadonly.value) return
  if (arrangingLayout.value) return
  try {
    await ElMessageBox.confirm(
      '将按从左到右、逐层方式自动整理当前流程图节点位置。可通过「上一步」撤销。是否继续？',
      '整理布局',
      {
        confirmButtonText: '开始整理',
        cancelButtonText: '取消',
        type: 'info'
      }
    )
  } catch {
    return
  }
  arrangingLayout.value = true
  await nextTick()
  await new Promise((resolve) => requestAnimationFrame(() => resolve()))
  try {
    const list = [...nodes.value]
    if (!list.length) return
    const levels = computeLayoutLevels(list, edges.value)
    const { roots, branchSetByNode } = computeBranchMembership(list, edges.value)
    const byId = Object.fromEntries(list.map((n) => [n.id, n]))

    const x0 = 70
    const yCenter = 260
    const colGap = 440
    const laneGap = 220
    const fallbackGap = 150
    const laneCount = Math.max(roots.length || 0, 1)
    const laneStartY = yCenter - ((laneCount - 1) * laneGap) / 2
    const laneY = (idx) => laneStartY + idx * laneGap

    for (let li = 0; li < levels.length; li += 1) {
      const lv = levels[li]
      let fallbackIdx = 0
      const laneUsed = new Map()
      for (let i = 0; i < lv.length; i += 1) {
        const id = lv[i]
        const n = byId[id]
        if (!n) continue
        const x = x0 + li * colGap
        const branches = branchSetByNode.get(id)
        let y = yCenter
        if (branches && branches.size === 1) {
          const idx = [...branches][0]
          const used = laneUsed.get(idx) || 0
          y = laneY(idx) + used * 18
          laneUsed.set(idx, used + 1)
        } else if (n.data?.kind === 'start' || n.data?.kind === 'userInput' || n.data?.kind === 'output') {
          y = yCenter
        } else {
          const dir = fallbackIdx % 2 === 0 ? 1 : -1
          const step = Math.floor(fallbackIdx / 2) + 1
          y = yCenter + dir * step * fallbackGap
          fallbackIdx += 1
        }
        n.position = { x, y }
      }
    }
    nodes.value = list.map((n) => ({ ...n, position: { ...n.position } }))
    edges.value = applyBranchEdgeColors(nodes.value, edges.value)
    pushHistory()
    await nextTick()
    fitView({ padding: 0.2, duration: 300 })
    ElMessage.success('已按层级自动整理布局')
  } finally {
    arrangingLayout.value = false
  }
}

function onDocKeydown(e) {
  if (workflowReadonly.value) return
  const t = e.target
  if (t && (t.closest?.('input') || t.closest?.('textarea') || t.isContentEditable)) return
  const mod = e.metaKey || e.ctrlKey
  if (!mod) return
  if (e.key === 'z' || e.key === 'Z') {
    if (e.shiftKey) redo()
    else undo()
    e.preventDefault()
  }
}

const version = computed(() => {
  const vid = Number(props.versionId)
  if (!app.value?.versions?.length || Number.isNaN(vid)) return null
  return app.value.versions.find((v) => v.id === vid) || null
})

const statusLabel = computed(() => {
  const s = version.value?.status
  if (s === 'designing') return '未发布'
  if (s === 'published') return '已发布'
  if (s === 'online') return '已上线'
  return '—'
})

const statusTagType = computed(() => {
  const s = version.value?.status
  if (s === 'designing') return 'info'
  if (s === 'published') return 'success'
  if (s === 'online') return 'warning'
  return 'info'
})

const selectedNode = computed(() => {
  const id = selectedNodeId.value
  if (!id) return null
  return nodes.value.find((n) => n.id === id) || null
})

const inspectorKind = computed(() => selectedNode.value?.data?.kind || '')
const inspectorDefaultTitle = computed(() => KIND_LABEL[inspectorKind.value] || '节点')
const inspectorKindLabel = computed(() => KIND_LABEL[inspectorKind.value] || inspectorKind.value)

const agentPickedLabel = computed(() => {
  if (!agentDraft.target_app_id) return ''
  const d = agentPickedDetail.value
  if (d && Number(d.id) === Number(agentDraft.target_app_id)) return d.name || ''
  return `应用 #${agentDraft.target_app_id}`
})

function formatVersionStatusLabel(status) {
  if (status === 'designing') return '编排中'
  if (status === 'published') return '已发布'
  if (status === 'online') return '已上线'
  return status || '—'
}

function formatAgentVersionLabel(v) {
  if (!v) return '—'
  const parts = []
  if (v.name) parts.push(v.name)
  const st = formatVersionStatusLabel(v.status)
  if (st) parts.push(st)
  if (v.mode) parts.push(v.mode)
  if (v.is_output) parts.push('默认输出')
  return parts.join(' · ')
}

async function refreshAgentApps() {
  agentPickerLoading.value = true
  try {
    const rows = await agentAppApi.listAgentApps({
      skip: 0,
      limit: 50,
      keyword: agentPickerKeyword.value || undefined
    })
    agentPickerApps.value = Array.isArray(rows) ? rows : []
  } finally {
    agentPickerLoading.value = false
  }
}

async function ensureAgentDetail(appId) {
  if (!appId) {
    agentPickedDetail.value = null
    return
  }
  const cur = Number(appId)
  agentDetailFetchSeq += 1
  const token = agentDetailFetchSeq
  const detail = await agentAppApi.getAgentApp(cur)
  if (token !== agentDetailFetchSeq) return
  agentPickedDetail.value = detail
}

async function openAgentPickerDialog() {
  agentPickerVisible.value = true
  await refreshAgentApps()
}

async function pickAgentApp(a) {
  if (!a?.id) return
  // 备份：如果用户在第二步取消，不要污染当前节点配置
  agentVersionBackup.value = {
    appId: agentDraft.target_app_id,
    versionId: agentDraft.target_version_id
  }
  agentDraft.target_app_id = a.id
  agentDraft.target_version_id = null

  await ensureAgentDetail(a.id)
  agentVersionOptions.value = agentPickedDetail.value?.versions || []
  agentVersionSelectValue.value = DEFAULT_OUTPUT_SENTINEL

  agentPickerVisible.value = false
  agentVersionDialogVisible.value = true
}

function cancelAgentVersion() {
  agentDraft.target_app_id = agentVersionBackup.value.appId
  agentDraft.target_version_id = agentVersionBackup.value.versionId
  agentVersionDialogVisible.value = false
  ensureAgentDetail(agentVersionBackup.value.appId).catch(() => {})
}

function confirmAgentVersion() {
  const val = agentVersionSelectValue.value
  agentDraft.target_version_id = val === DEFAULT_OUTPUT_SENTINEL ? null : Number(val)
  const chosenNodeId = selectedNodeId.value
  agentVersionDialogVisible.value = false

  const appId = agentDraft.target_app_id
  const versionId = agentDraft.target_version_id || agentVersionOptions.value.find(v => v.is_output)?.id

  if (appId && versionId) {
    agentAppApi.getAgentVersionParams(appId, versionId).then(res => {
      if (selectedNodeId.value !== chosenNodeId || agentDraft.target_app_id !== appId || agentDraft.target_version_id !== (val === DEFAULT_OUTPUT_SENTINEL ? null : Number(val))) return
      const data = res.data || res
      if (data.input_params?.length) {
        agentInputRows.value = data.input_params.map(p => normalizeAgentInputRow({
          target_field: p.name,
          source_mode: p.source_type === 'constant' ? 'const' : 'ref',
          source_ref: '',
          const_value: p.constant_value ?? p.default_value ?? '',
          param_type: p.type || 'STRING',
          required: p.required || false,
          default_value: p.default_value ?? '',
          description: p.description || ''
        }))
      } else {
        agentInputRows.value = []
      }
      if (data.output_params?.length) {
        agentOutputRows.value = data.output_params.map(p => normalizeAgentOutputRow({
          source_field: p.name,
          target_var: p.name,
          param_type: p.type || 'STRING',
          description: p.description || ''
        }))
      } else {
        agentOutputRows.value = []
      }
      commitAgentMappings()
    }).catch(e => ElMessage.error(e.message || '无法加载目标工作流参数，请手动配置'))
  } else {
    agentInputRows.value = []
    agentOutputRows.value = []
    commitAgentMappings()
  }

  commitAgentConfig()
}

async function openAgentVersionDialog() {
  if (!agentDraft.target_app_id) return
  agentVersionBackup.value = {
    appId: agentDraft.target_app_id,
    versionId: agentDraft.target_version_id
  }

  await ensureAgentDetail(agentDraft.target_app_id)
  agentVersionOptions.value = agentPickedDetail.value?.versions || []

  agentVersionSelectValue.value =
    agentDraft.target_version_id == null ? DEFAULT_OUTPUT_SENTINEL : agentDraft.target_version_id
  agentVersionDialogVisible.value = true
}

function clearAgentSelection() {
  agentDraft.target_app_id = null
  agentDraft.target_version_id = null
  agentPickedDetail.value = null
  agentInputRows.value = []
  agentOutputRows.value = []
  commitAgentMappings()
  commitAgentConfig()
}

async function refreshLabProjects() {
  labPickerLoading.value = true
  try {
    const rows = await listAutobiProjects({ skip: 0, limit: 200 })
    labPickerProjects.value = Array.isArray(rows) ? rows : []
  } finally {
    labPickerLoading.value = false
  }
}

async function ensureLabProjectDetail(projectId) {
  if (!projectId) {
    labPickedProject.value = null
    return
  }
  const cur = Number(projectId)
  labDetailFetchSeq += 1
  const token = labDetailFetchSeq
  const p = await getAutobiProject(cur)
  if (token !== labDetailFetchSeq) return
  labPickedProject.value = p
}

async function openLabPickerDialog() {
  labPickerVisible.value = true
  if (!labPickerProjects.value?.length) {
    await refreshLabProjects()
  }
}

async function pickLabProject(p) {
  if (!p?.id) return
  labPickedProject.value = p
  labDraft.project_id = p.id
  labPickerVisible.value = false
  commitLabConfig()
}

function clearLabSelection() {
  labDraft.project_id = null
  labPickedProject.value = null
  commitLabConfig()
}

const agentPickedVersionLabel = computed(() => {
  if (!agentDraft.target_app_id) return ''
  if (agentDraft.target_version_id == null) return '默认当前版本'
  const d = agentPickedDetail.value
  const v = d?.versions?.find((x) => Number(x.id) === Number(agentDraft.target_version_id))
  if (!v) return `版本 #${agentDraft.target_version_id}`
  return `${v.name} · ${formatVersionStatusLabel(v.status)}`
})

const labPickedLabel = computed(() => {
  if (!labDraft.project_id) return ''
  const p = labPickedProject.value
  if (p && Number(p.id) === Number(labDraft.project_id)) return p.name || ''
  return `项目 #${labDraft.project_id}`
})

const labPickedDescription = computed(() => {
  const p = labPickedProject.value
  if (!p) return ''
  return p.description || ''
})

const labPickerFilteredProjects = computed(() => {
  const kw = (labPickerKeyword.value || '').trim().toLowerCase()
  if (!kw) return labPickerProjects.value
  return (labPickerProjects.value || []).filter((p) => {
    const name = (p.name || '').toLowerCase()
    const desc = (p.description || '').toLowerCase()
    return name.includes(kw) || desc.includes(kw)
  })
})

/** 用户输入字段：类型选项（与后端 executor 宽松存储 type 字符串） */
const userInputFieldTypeOptions = [
  { value: 'string', label: 'STRING（文本）' },
  { value: 'number', label: 'NUMBER（数字）' },
  { value: 'boolean', label: 'BOOL（布尔）' },
  { value: 'object', label: 'OBJECT（对象）' },
  { value: 'array_string', label: 'LIST<String>' },
  { value: 'array_number', label: 'LIST<Number>' },
  { value: 'array_boolean', label: 'LIST<Bool>' },
  { value: 'array_object', label: 'LIST<Object>' }
]

const userInputSourceModeOptions = [
  { value: 'ref', label: '引用' },
  { value: 'const', label: '常量' }
]

/** 来源为「引用」时的级联：输入信息 / 会话 → 具体字段 */
const userInputSourceCascaderOptions = [
  {
    value: 'input',
    label: '输入信息',
    children: [
      { value: 'input', label: '用户输入(input)' },
      { value: 'attachments', label: '附件(attachments)' },
      { value: 'metadata', label: '附加信息(metadata)' }
    ]
  },
  {
    value: 'session',
    label: '会话',
    children: [{ value: 'conversation_id', label: '会话ID' }]
  }
]

const inspectorIcon = computed(() => {
  const k = inspectorKind.value
  if (k === 'start') return VideoPlay
  if (k === 'userInput') return House
  if (k === 'llm') return Cpu
  if (k === 'script') return Document
  if (k === 'selector') return Share
  if (k === 'agent') return Avatar
  if (k === 'lab') return MagicStick
  if (k === 'atomic') return SetUp
  if (k === 'externalApi') return Link
  if (k === 'output') return Flag
  return Cpu
})

function parseProviderModels(modelsStr) {
  if (!modelsStr) return []
  try {
    const a = JSON.parse(modelsStr)
    return Array.isArray(a) ? a : []
  } catch {
    return []
  }
}

const llmModelOptions = computed(() => {
  const p = modelProviders.value.find((x) => x.id === llmDraft.provider_id)
  return p ? parseProviderModels(p.models) : []
})

function collectUpstreamNodeIds(targetId) {
  const preds = new Map()
  for (const e of edges.value) {
    if (!preds.has(e.target)) preds.set(e.target, [])
    preds.get(e.target).push(e.source)
  }
  const seen = new Set()
  const st = [...(preds.get(targetId) || [])]
  while (st.length) {
    const u = st.pop()
    if (seen.has(u)) continue
    seen.add(u)
    for (const p of preds.get(u) || []) st.push(p)
  }
  return seen
}

function outputsForNode(node) {
  const capability = node.data?.atomic_config?.capability || 'elasticsearch-value-retriever'
  return nodeOutputOptions(node, atomicCapabilitySpec(capability).outputs)
}

const selectedNodeIssues = computed(() => selectedNode.value ? nodeConfigurationIssues(selectedNode.value) : [])

const upstreamVarOptions = computed(() => {
  const sid = selectedNodeId.value
  if (!sid) return []
  const ups = collectUpstreamNodeIds(sid)
  const opts = []
  for (const nid of ups) {
    const node = nodes.value.find((n) => n.id === nid)
    if (node) opts.push(...outputsForNode(node))
  }
  return opts
})

const nodeDescription = ref('')

watch(
  () => [selectedNodeId.value, inspectorReloadKey.value],
  ([id]) => {
    if (!id) {
      nodeDescription.value = ''
      return
    }
    const n = nodes.value.find((x) => x.id === id)
    nodeDescription.value = (n?.data && n.data.description) || ''
  },
  { immediate: true }
)

function normalizeUserInputFieldRow(r) {
  const row = { ...r }
  if (!row.source_mode) row.source_mode = 'const'
  if (row.source_mode === 'ref') {
    if (!Array.isArray(row.source_ref) || row.source_ref.length < 2) {
      row.source_ref = ['input', 'input']
    }
  } else {
    row.source_ref = undefined
  }
  if (row.description == null) row.description = ''
  if (row.display == null) row.display = row.variable || ''
  if (!row.type) row.type = 'string'
  if (row.default != null && typeof row.default === 'object') row.default = formatWorkflowValue(row.default)
  return row
}

function normalizeScriptInputRow(r) {
  const row = { ...r }
  if (!row.name) row.name = ''
  if (!row.source_mode) row.source_mode = 'ref'
  if (!row.ref) row.ref = ''
  if (!row.type) row.type = 'string'
  if (row.const_value == null) row.const_value = ''
  else row.const_value = formatWorkflowValue(row.const_value)
  return row
}

function normalizeScriptOutputRow(r) {
  const row = { ...r }
  if (!row.name) row.name = ''
  if (!row.type) row.type = 'string'
  return row
}

function normalizeAgentInputRow(r) {
  const row = { ...r }
  if (!row.target_field) row.target_field = ''
  if (!row.source_mode) row.source_mode = 'ref'
  if (!row.source_ref) row.source_ref = row.source_var || ''
  if (row.const_value == null) row.const_value = ''
  else row.const_value = formatWorkflowValue(row.const_value)
  if (!row.param_type) row.param_type = 'STRING'
  if (!row.required) row.required = false
  if (row.default_value == null) row.default_value = ''
  if (!row.description) row.description = ''
  return row
}

function normalizeAgentOutputRow(r) {
  const row = { ...r }
  if (!row.source_field) row.source_field = ''
  if (!row.target_var) row.target_var = ''
  if (!row.param_type) row.param_type = 'STRING'
  if (!row.description) row.description = ''
  return row
}

function atomicCapabilitySpec(value) {
  return ATOMIC_CAPABILITIES.find((x) => x.value === value) || ATOMIC_CAPABILITIES[0]
}

function normalizeAtomicInputRows(capability, rows = []) {
  return buildAtomicInputRows(capability, rows)
}

function normalizeAtomicOutputRows(capability) {
  const spec = atomicCapabilitySpec(capability)
  return (spec.outputs || []).map((x) => ({ ...x }))
}

const atomicPrimaryRows = computed(() => atomicInputRows.value.filter((r) => !r.advanced))
const atomicAdvancedRows = computed(() => atomicInputRows.value.filter((r) => r.advanced))
const isAtomicGenerateSql = computed(() => atomicDraft.capability === 'generate-sql')

const atomicModelProviderOptions = computed(() =>
  (modelProviders.value || []).map((p) => ({
    value: String(p.id),
    label: p.name || `供应商 #${p.id}`
  }))
)

function atomicRowByKey(key) {
  return atomicInputRows.value.find((r) => r.key === key)
}

const atomicModelNameOptions = computed(() => {
  const providerRow = atomicRowByKey('provider_id')
  if (!providerRow || providerRow.source_mode === 'ref') return []
  const providerId = Number(providerRow.const_value)
  const provider = (modelProviders.value || []).find((p) => Number(p.id) === providerId)
  return provider ? parseProviderModels(provider.models) : []
})

function atomicConstControl(row) {
  if (['knowledgeBase', 'modelProvider', 'modelName'].includes(row.control)) return 'el-select'
  if (row.multiline) return 'el-input'
  return 'el-input'
}

function atomicConstProps(row) {
  if (row.control === 'knowledgeBase') return { size: 'small', filterable: true, clearable: true, placeholder: row.required ? '请选择知识库（必填）' : '知识库可选，留空仅使用提示词上下文' }
  if (row.control === 'modelProvider') return { size: 'small', filterable: true, placeholder: '请选择供应商' }
  if (row.control === 'modelName') {
    return {
      size: 'small',
      filterable: true,
      allowCreate: true,
      placeholder: atomicModelNameOptions.value.length ? '请选择模型' : '先选择供应商或手动输入'
    }
  }
  const placeholder = atomicConstPlaceholder(row)
  if (row.multiline) return { size: 'small', type: 'textarea', rows: row.key === 'sql' ? 5 : 3, placeholder }
  return { size: 'small', placeholder }
}

function atomicConstPlaceholder(row) {
  const key = row.key
  if (key === 'query') return '可输入文本，也可切换为引用上游变量'
  if (key === 'sql') return 'SELECT ...\n仅允许查询语句'
  if (key === 'table_name' && row.type === 'LIST<String>') return 'JSON 数组，例如 ["表A.字段1", "表B.字段2"]'
  if (key === 'table_name') return '可留空；或填写表名、表名.字段名、表名&&字段名'
  if (key === 'entity') return 'JSON 数组，例如 ["上海", "年份"]'
  if (key === 'score_threshold') return 'null 表示不过滤；也可填 0.3'
  if (key === 'top_k') return '默认已填，可按需修改'
  if (key === 'extra_context') return '可选补充上下文；复杂对象请填 JSON 字符串或切换引用'
  if (['temperature', 'max_tokens', 'top_p'].includes(key)) return '默认已填，可按需修改'
  if (row.type?.startsWith('LIST')) return '请填写 JSON 数组，例如 ["值1", "值2"]'
  if (row.type === 'OBJECT') return '请填写 JSON 对象，例如 {"key":"value"}'
  if (row.type === 'NUMBER') return '请输入有效数字；可选参数留空使用默认值'
  return '请输入常量值'
}

function onAtomicRowModeChange(row) {
  if (row.source_mode === 'ref') {
    row.source_ref = row.source_ref || ''
  }
  commitAtomicConfig()
}

function normalizeAtomicContextRows(rows = []) {
  const base = Array.isArray(rows) && rows.length
    ? rows
    : [
        { name: 'knowledge', source_mode: 'ref', source_ref: '', const_value: '' },
        { name: 'examples', source_mode: 'ref', source_ref: '', const_value: '' }
      ]
  return base.map((r) => ({
    name: r.name || '',
    source_mode: r.source_mode === 'const' ? 'const' : 'ref',
    source_ref: r.source_ref || r.ref || '',
    const_value: r.const_value != null ? String(r.const_value) : ''
  }))
}

function addAtomicContextRow() {
  atomicContextRows.value.push({ name: '', source_mode: 'ref', source_ref: '', const_value: '' })
  commitAtomicConfig()
}

function removeAtomicContextRow(idx) {
  atomicContextRows.value.splice(idx, 1)
  commitAtomicConfig()
}

function normalizeApiOutputRow(r) {
  const row = { ...r }
  if (!row.name) row.name = ''
  if (!row.json_path) row.json_path = ''
  return row
}

function onUserInputSourceMode(row) {
  if (row.source_mode === 'ref') {
    if (!Array.isArray(row.source_ref) || row.source_ref.length < 2) {
      row.source_ref = ['input', 'input']
    }
  }
  commitUserInputFields()
}

watch(
  () => [selectedNodeId.value, inspectorReloadKey.value],
  () => {
    const n = selectedNode.value
    if (!n?.data) return
    const d = n.data
    inspectorLabelDraft.value = (d.label || '').trim() || KIND_LABEL[d.kind] || '节点'
    const rawFields = JSON.parse(JSON.stringify(d.fields || []))
    userInputFieldRows.value = rawFields.map((x) => normalizeUserInputFieldRow(x))
    scriptInputRows.value = (d.script_config?.input_vars || []).map((x) => normalizeScriptInputRow(x))
    scriptOutputRows.value = (d.script_config?.output_vars || []).map((x) => normalizeScriptOutputRow(x))
    agentInputRows.value = (d.agent_config?.input_mapping || []).map((x) => normalizeAgentInputRow({
      ...x,
      source_ref: x.source_var || x.source_ref || '',
      source_mode: x.source_mode || (x.const_value != null && x.const_value !== '' ? 'const' : 'ref')
    }))
    agentOutputRows.value = (d.agent_config?.output_mapping || []).map((x) => normalizeAgentOutputRow(x))
    agentSseOutputThoughts.value = d.agent_config?.sse_output_thoughts !== false
    agentSseOutputResults.value = d.agent_config?.sse_output_results !== false
    atomicDraft.capability = d.atomic_config?.capability || 'elasticsearch-value-retriever'
    atomicInputRows.value = normalizeAtomicInputRows(atomicDraft.capability, d.atomic_config?.input_vars || [])
    atomicSystemPrompt.value = d.atomic_config?.system_prompt || DEFAULT_GENERATE_SQL_PROMPT
    atomicContextRows.value = normalizeAtomicContextRows(d.atomic_config?.context_vars || [])
    apiOutputRows.value = (d.api_config?.output_vars || []).map((x) => normalizeApiOutputRow(x))
    outputTemplateDraft.value = d.output_config?.content_template || d.output_template || ''
    outputContentRows.value = d.output_config?.content_fields?.length
      ? JSON.parse(JSON.stringify(d.output_config.content_fields))
      : []
    outputMetadataRows.value = d.output_config?.metadata_fields?.length
      ? JSON.parse(JSON.stringify(d.output_config.metadata_fields))
      : []
    scriptCodeDraft.value = d.script_config?.code || ''
    const labIm = d.lab_config?.input_mapping || []
    const contentMap = labIm.find((m) => ['content', 'query'].includes(m.target_field || m.target || 'content'))
    if (!contentMap) {
      labContentMode.value = 'const'
      labContentConstText.value = ''
      labContentRef.value = ''
    } else if (contentMap?.source_mode === 'const') {
      labContentMode.value = 'const'
      labContentConstText.value = contentMap?.const_value || ''
      labContentRef.value = ''
    } else {
      labContentMode.value = 'ref'
      labContentRef.value =
        contentMap?.source_ref || contentMap?.source_var || d.lab_config?.content_ref || ''
      labContentConstText.value = ''
    }
    const featuresMap = labIm.find((m) => (m.target_field || '') === 'features')
    if (!featuresMap) {
      labFeaturesConstObj.value = {}
    } else {
      try {
        labFeaturesConstObj.value = JSON.parse(featuresMap?.const_value || '{}')
      } catch {
        labFeaturesConstObj.value = {}
      }
    }
    const ov = d.lab_config?.output_vars
    labOutputVars.value = Array.isArray(ov) && ov.length ? ov : [...LAB_OUTPUT_FIELDS]
    labSseOutputThoughts.value = d.lab_config?.sse_output_thoughts !== false
    labSseOutputResults.value = d.lab_config?.sse_output_results !== false
    const useLlmUser = !!d.llm_config?.use_user_prompt_template
    llmInputParamRows.value = (d.llm_config?.input_params || []).map((x) => ({
      variable: (x.variable || '').trim(),
      source_mode: (x.source_mode || 'ref').trim(),
      ref: (x.ref || '').trim(),
      default: x.default != null ? String(x.default) : ''
    }))
    if (!llmInputParamRows.value.length) {
      llmInputParamRows.value = [{ variable: 'input', source_mode: 'ref', ref: '用户输入.input', default: '' }]
    }
    llmStopWords.value = d.llm_config?.stop_words || []
    llmStopWordsText.value = (d.llm_config?.stop_words || []).join('\n')
    Object.assign(llmDraft, {
      provider_id: d.llm_config?.provider_id ?? null,
      model_name: d.llm_config?.model_name || '',
      temperature: d.llm_config?.temperature ?? 0.7,
      max_tokens: d.llm_config?.max_tokens ?? 2000,
      top_p: d.llm_config?.top_p ?? 0.9,
      context_vars: useLlmUser ? [...(d.llm_config?.context_vars || [])] : [],
      system_prompt: d.llm_config?.system_prompt || '',
      use_user_prompt_template: useLlmUser,
      user_prompt: d.llm_config?.user_prompt || '',
      param_bindings: JSON.parse(JSON.stringify(d.llm_config?.param_bindings || {})),
      input_params: llmInputParamRows.value,
      stop_words: d.llm_config?.stop_words || [],
      output_params: d.llm_config?.output_params || []
    })
    Object.assign(agentDraft, {
      target_app_id: d.agent_config?.target_app_id ?? null,
      target_version_id: d.agent_config?.target_version_id ?? null
    })
    ensureAgentDetail(d.agent_config?.target_app_id ?? null).catch(() => {})
    Object.assign(labDraft, { project_id: d.lab_config?.project_id ?? null })
    ensureLabProjectDetail(d.lab_config?.project_id ?? null).catch(() => {})
    Object.assign(apiDraft, {
      method: d.api_config?.method || 'GET',
      base_url: d.api_config?.base_url || '',
      path: d.api_config?.path || '',
      timeout: d.api_config?.timeout ?? 60,
      headers: JSON.parse(JSON.stringify(d.api_config?.headers || [])),
      query: JSON.parse(JSON.stringify(d.api_config?.query || [])),
      body_template: d.api_config?.body_template || ''
    })
    if (d.kind === 'selector') {
      const raw = d.selector_config?.cases?.length
        ? JSON.parse(JSON.stringify(d.selector_config.cases))
        : [
            { id: 'case-0', relation: 'AND', conditions: [{ ref: '', op: 'starts_with', value: '' }] },
            { id: 'case-1', relation: 'AND', conditions: [{ ref: '', op: 'eq', value: '' }] }
          ]
      selectorCaseRows.value = raw.map((c, idx) => ({
        id: (c.id && String(c.id)) || `case-${idx}`,
        relation: c.relation || 'AND',
        conditions: (c.conditions || []).map((x) => ({
          ref: x.ref || '',
          op: x.op || 'eq',
          value: x.value != null ? String(x.value) : ''
        }))
      }))
    } else {
      selectorCaseRows.value = []
    }
  },
  // 只在切换节点或撤销/重做时回填，避免提交一个字段时抹掉其他未提交的草稿。
  { immediate: true }
)

function persistNodeDescription() {
  const id = selectedNodeId.value
  if (!id) return
  const text = nodeDescription.value
  nodes.value = nodes.value.map((n) =>
    n.id === id ? { ...n, data: { ...n.data, description: text } } : n
  )
  pushHistory()
}

function paletteIcon(kind) {
  const map = {
    llm: Cpu,
    script: Document,
    selector: Share,
    agent: Avatar,
    lab: MagicStick,
    atomic: SetUp,
    externalApi: Link,
    output: Flag
  }
  return map[kind] || Cpu
}

function allocateNodeLabel(baseLabel, excludeNodeId = null) {
  const base = (baseLabel || '节点').trim() || '节点'
  const used = new Set(
    nodes.value
      .filter((n) => !excludeNodeId || n.id !== excludeNodeId)
      .map((n) => (n.data?.label || '').trim())
      .filter(Boolean)
  )
  if (!used.has(base)) return base
  let i = 2
  while (used.has(`${base}_${i}`)) i += 1
  return `${base}_${i}`
}

function buildNewNodeData(kind, label) {
  const base = { kind, label: allocateNodeLabel(label || KIND_LABEL[kind] || kind) }
  if (kind === 'llm') {
    return {
      ...base,
      llm_config: {
        provider_id: null,
        model_name: '',
        temperature: 0.7,
        max_tokens: 2000,
        top_p: 0.9,
        context_vars: [],
        system_prompt: '',
        use_user_prompt_template: false,
        user_prompt: '',
        param_bindings: {}
      }
    }
  }
  if (kind === 'script') {
    return {
      ...base,
      script_config: {
        code:
          'def main(arg1: str):\n' +
          '    return {\n' +
          '        "result": arg1,\n' +
          '    }\n',
        input_vars: [{ name: 'arg1', source_mode: 'ref', ref: '', type: 'string' }],
        output_vars: [{ name: 'result', type: 'string' }]
      }
    }
  }
  if (kind === 'agent') {
    return {
      ...base,
      agent_config: {
        target_app_id: null,
        target_version_id: null,
        input_mapping: [],
        output_mapping: [],
        sse_output_thoughts: true,
        sse_output_results: true
      }
    }
  }
  if (kind === 'lab') {
    return {
      ...base,
      lab_config: { project_id: null, input_mapping: [], sse_output_thoughts: true, sse_output_results: true }
    }
  }
  if (kind === 'atomic') {
    const capability = 'elasticsearch-value-retriever'
    return {
      ...base,
      atomic_config: {
        capability,
        input_vars: normalizeAtomicInputRows(capability),
        output_vars: normalizeAtomicOutputRows(capability)
      }
    }
  }
  if (kind === 'externalApi') {
    return {
      ...base,
      api_config: {
        method: 'GET',
        base_url: '',
        path: '',
        timeout: 60,
        headers: [],
        query: [],
        output_vars: []
      }
    }
  }
  if (kind === 'selector') {
    return {
      ...base,
      selector_config: {
        cases: [
          { id: 'case-0', conditions: [{ ref: '', op: 'starts_with', value: '' }] },
          { id: 'case-1', conditions: [{ ref: '', op: 'eq', value: '' }] }
        ]
      }
    }
  }
  if (kind === 'output') {
    return { ...base, output_config: { content_template: '' } }
  }
  return { ...base }
}

function ensureGraphMeta() {
  let draft = nodes.value.map((n) => ({ ...n, data: { ...(n.data || {}) } }))
  draft = draft.map((n) => {
    const d = n.data
    let type = n.type || 'wfCard'
    if (d.kind === 'selector') type = 'wfSelector'
    else if (type === 'wfSelector' && d.kind !== 'selector') type = 'wfCard'
    if (d.kind === 'output' && Object.prototype.hasOwnProperty.call(d, 'output_template')) {
      d.output_config = { ...(d.output_config || {}), content_template: String(d.output_template ?? '') }
      delete d.output_template
    }
    if (
      d.kind === 'lab' &&
      d.lab_config?.content_ref &&
      !(d.lab_config.input_mapping && d.lab_config.input_mapping.length)
    ) {
      d.lab_config = {
        ...d.lab_config,
        input_mapping: [{ target_field: 'content', source_var: d.lab_config.content_ref }]
      }
    }
    return { ...n, type, data: d }
  })
  const usedLabels = new Set()
  draft = draft.map((n) => {
    const d = n.data
    let label = (d.label || '').trim()
    if (d.kind === 'start') label = '开始'
    if (!label) label = KIND_LABEL[d.kind] || '节点'
    if (usedLabels.has(label)) {
      let i = 2
      while (usedLabels.has(`${label}_${i}`)) i += 1
      label = `${label}_${i}`
    }
    usedLabels.add(label)
    d.label = label
    return { ...n, data: d }
  })
  nodes.value = draft
}

function updateSelectedNodeData(partialData) {
  partialData = JSON.parse(JSON.stringify(partialData))
  const id = selectedNodeId.value
  if (!id) return
  nodes.value = nodes.value.map((n) => {
    if (n.id !== id) return n
    const d = { ...n.data }
    for (const [k, v] of Object.entries(partialData)) {
      if (
        v &&
        typeof v === 'object' &&
        !Array.isArray(v) &&
        d[k] &&
        typeof d[k] === 'object' &&
        !Array.isArray(d[k])
      ) {
        d[k] = { ...d[k], ...v }
      } else {
        d[k] = v
      }
    }
    return { ...n, data: d }
  })
  pushHistory()
}

function commitNodeLabel() {
  const id = selectedNodeId.value
  if (!id) return
  if (inspectorKind.value === 'start') return
  const raw = inspectorLabelDraft.value.trim()
  if (!raw) {
    ElMessage.warning('节点名称不能为空')
    const n = selectedNode.value
    inspectorLabelDraft.value = (n?.data?.label || '').trim() || KIND_LABEL[n?.data?.kind] || '节点'
    return
  }
  const dup = nodes.value.some((n) => n.id !== id && (n.data?.label || '').trim() === raw)
  if (dup) {
    ElMessage.warning('节点名称已存在，请改为唯一名称')
    inspectorLabelDraft.value = selectedNode.value?.data?.label || ''
    return
  }
  const previous = selectedNode.value?.data?.label
  if (previous && previous !== raw) nodes.value = renameNodeReferences(nodes.value, previous, raw)
  updateSelectedNodeData({ label: raw })
}

function commitUserInputFields() {
  const rows = userInputFieldRows.value.filter((r) => (r.variable || '').trim())
  if (!rows.length) {
    ElMessage.warning('至少保留一个输入字段')
    return
  }
  const names = rows.map((r) => r.variable.trim())
  if (new Set(names).size !== names.length) {
    ElMessage.warning('字段「名称」不能重复')
    return
  }
  updateSelectedNodeData({
    fields: rows.map((r) => {
      const mode = r.source_mode || 'const'
      const base = {
        variable: r.variable.trim(),
        display: (r.display || r.variable).trim(),
        type: r.type || 'string',
        required: !!r.required,
        hidden: !!r.hidden,
        description: (r.description || '').trim(),
        source_mode: mode,
        maxLength: r.maxLength ?? null
      }
      if (mode === 'const') {
        base.default = r.default ?? ''
        base.source_ref = undefined
      } else {
        base.source_ref = Array.isArray(r.source_ref) && r.source_ref.length >= 2 ? [...r.source_ref] : ['input', 'input']
        base.default = r.default ?? ''
      }
      return base
    })
  })
}

function addUserInputFieldRow() {
  userInputFieldRows.value.push(
    normalizeUserInputFieldRow({
      variable: '',
      display: '',
      type: 'string',
      required: false,
      hidden: false,
      default: '',
      description: '',
      source_mode: 'const',
      maxLength: null
    })
  )
}

function removeUserInputFieldRow(idx) {
  if (userInputFieldRows.value.length <= 1) {
    ElMessage.warning('至少保留一个输入字段')
    return
  }
  userInputFieldRows.value.splice(idx, 1)
  commitUserInputFields()
}

function commitOutputTemplate() {
  updateSelectedNodeData({
    output_config: {
      content_template: outputTemplateDraft.value || '',
      content_fields: outputContentRows.value,
      metadata_fields: outputMetadataRows.value
    }
  })
}

function addOutputContentRow() {
  outputContentRows.value.push({ output_format: 'text', source_ref: '', source_mode: 'ref', const_value: '' })
}

function removeOutputContentRow(idx) {
  outputContentRows.value.splice(idx, 1)
  commitOutputTemplate()
}

function addOutputMetadataRow() {
  outputMetadataRows.value.push({ name: '', source_ref: '', source_mode: 'ref', type: 'STRING', const_value: '' })
}

function removeOutputMetadataRow(idx) {
  outputMetadataRows.value.splice(idx, 1)
  commitOutputTemplate()
}

function commitLlmConfig() {
  const pb = {}
  for (const k of llmNamedSlotKeys.value) {
    const row = llmDraft.param_bindings[k] || {}
    pb[k] = {
      source_mode: row.source_mode === 'const' ? 'const' : 'ref',
      ref: (row.ref || '').trim(),
      const_value: row.const_value != null ? String(row.const_value) : ''
    }
  }
  const useUser = !!llmDraft.use_user_prompt_template
  updateSelectedNodeData({
    llm_config: {
      provider_id: llmDraft.provider_id,
      model_name: (llmDraft.model_name || '').trim(),
      temperature: llmDraft.temperature,
      max_tokens: llmDraft.max_tokens,
      top_p: llmDraft.top_p,
      context_vars: useUser ? [...(llmDraft.context_vars || [])] : [],
      system_prompt: llmDraft.system_prompt || '',
      use_user_prompt_template: useUser,
      user_prompt: llmDraft.user_prompt || '',
      param_bindings: pb,
      input_params: llmInputParamRows.value,
      stop_words: llmStopWords.value,
      output_params: LLM_OUTPUT_FIELDS
    }
  })
}

function onLlmUserPromptSwitch() {
  if (!llmDraft.use_user_prompt_template) {
    llmDraft.context_vars = []
  }
  commitLlmConfig()
}

function onLlmProviderChange() {
  const opts = llmModelOptions.value
  if (llmDraft.model_name && !opts.includes(llmDraft.model_name)) {
    llmDraft.model_name = opts[0] || ''
  }
  commitLlmConfig()
}

function commitScriptConfig() {
  const prev = selectedNode.value?.data?.script_config || {}
  updateSelectedNodeData({
    script_config: {
      ...prev,
      code: scriptCodeDraft.value || ''
    }
  })
}

function commitScriptParams() {
  const prev = selectedNode.value?.data?.script_config || {}
  updateSelectedNodeData({
    script_config: {
      ...prev,
      input_vars: scriptInputRows.value
        .map((r) => {
          const base = { name: (r.name || '').trim(), type: r.type || 'string' }
          if (r.source_mode === 'const') {
            base.source_mode = 'const'
            base.const_value = r.const_value ?? ''
            base.ref = ''
          } else {
            base.source_mode = 'ref'
            base.ref = (r.ref || '').trim()
          }
          return base
        }),
      output_vars: scriptOutputRows.value
        .map((r) => ({ name: (r.name || '').trim(), type: r.type || 'string' }))
    }
  })
}

function addScriptInputRow() {
  scriptInputRows.value.push(normalizeScriptInputRow({ name: '', source_mode: 'ref', ref: '', const_value: '', type: 'string' }))
}

function removeScriptInputRow(idx) {
  scriptInputRows.value.splice(idx, 1)
  commitScriptParams()
}

function addScriptOutputRow() {
  scriptOutputRows.value.push(normalizeScriptOutputRow({ name: '', type: 'string' }))
}

function removeScriptOutputRow(idx) {
  scriptOutputRows.value.splice(idx, 1)
  commitScriptParams()
}

function addLlmInputParamRow() {
  llmInputParamRows.value.push({ variable: '', source_mode: 'ref', ref: '', default: '' })
}

function removeLlmInputParamRow(idx) {
  if (llmInputParamRows.value.length <= 1) {
    ElMessage.warning('至少保留一个输入参数')
    return
  }
  llmInputParamRows.value.splice(idx, 1)
  commitLlmInputParams()
}

function commitLlmInputParams() {
  llmDraft.input_params = llmInputParamRows.value
  commitLlmConfig()
}

function commitLlmStopWords() {
  const lines = (llmStopWordsText.value || '').split('\n').map((s) => s.trim()).filter(Boolean)
  llmStopWords.value = lines
  llmDraft.stop_words = lines
  commitLlmConfig()
}

function commitAgentConfig() {
  const prev = selectedNode.value?.data?.agent_config || {}
  updateSelectedNodeData({
    agent_config: {
      ...prev,
      target_app_id: agentDraft.target_app_id,
      target_version_id: agentDraft.target_version_id,
      sse_output_thoughts: agentSseOutputThoughts.value !== false,
      sse_output_results: agentSseOutputResults.value !== false
    }
  })
}

function commitAgentSseConfig() {
  const prev = selectedNode.value?.data?.agent_config || {}
  updateSelectedNodeData({
    agent_config: {
      ...prev,
      sse_output_thoughts: agentSseOutputThoughts.value !== false,
      sse_output_results: agentSseOutputResults.value !== false
    }
  })
}

function commitAgentMappings() {
  const prev = selectedNode.value?.data?.agent_config || {}
  updateSelectedNodeData({
    agent_config: {
      ...prev,
      input_mapping: agentInputRows.value
        .map((r) => {
          const mode = r.source_mode || 'ref'
          const item = {
            target_field: (r.target_field || '').trim(),
            source_mode: mode,
            param_type: r.param_type, required: !!r.required, default_value: r.default_value, description: r.description
          }
          if (mode === 'const') {
            item.const_value = r.const_value ?? ''
            item.source_var = ''
          } else {
            item.source_var = (r.source_ref || '').trim()
          }
          return item
        }),
      output_mapping: agentOutputRows.value
        .map((r) => ({
          source_field: (r.source_field || '').trim(),
          target_var: (r.target_var || '').trim(),
          param_type: r.param_type, description: r.description
        })),
      sse_output_thoughts: agentSseOutputThoughts.value !== false,
      sse_output_results: agentSseOutputResults.value !== false
    }
  })
}

function addAgentInputRow() {
  agentInputRows.value.push(normalizeAgentInputRow({ target_field: '', source_mode: 'ref', source_ref: '' }))
}

function removeAgentInputRow(idx) {
  agentInputRows.value.splice(idx, 1)
  commitAgentMappings()
}

function addAgentOutputRow() {
  agentOutputRows.value.push(normalizeAgentOutputRow({ source_field: '', target_var: '' }))
}

function removeAgentOutputRow(idx) {
  agentOutputRows.value.splice(idx, 1)
  commitAgentMappings()
}

function commitLabConfig() {
  const prev = selectedNode.value?.data?.lab_config || {}
  const contentRef = (labContentRef.value || '').trim()
  const contentConstText = (labContentConstText.value || '').trim()
  const input_mapping = []
  // 引用模式须始终写入 source_mode: ref，否则空 ref 会落库成 const，侧边栏 watch 会把单选钮打回「常量」
  if (labContentMode.value === 'ref') {
    input_mapping.push({
      target_field: 'content',
      source_mode: 'ref',
      source_ref: contentRef
    })
  } else {
    input_mapping.push({
      target_field: 'content',
      source_mode: 'const',
      const_value: contentConstText
    })
  }

  input_mapping.push({
    target_field: 'features',
    source_mode: 'const',
    const_value: JSON.stringify(labFeaturesConstObj.value || {})
  })

  updateSelectedNodeData({
    lab_config: {
      ...prev,
      project_id: labDraft.project_id,
      input_mapping,
      output_vars: Array.isArray(labOutputVars.value) ? labOutputVars.value : [...LAB_OUTPUT_FIELDS],
      sse_output_thoughts: labSseOutputThoughts.value !== false,
      sse_output_results: labSseOutputResults.value !== false
    }
  })
}

function commitAtomicConfig() {
  updateSelectedNodeData({
      atomic_config: {
        capability: atomicDraft.capability,
        input_vars: atomicInputRows.value.map((r) => ({
        key: r.key,
        type: r.type || 'STRING',
        source_mode: r.source_mode === 'ref' ? 'ref' : 'const',
        source_ref: r.source_mode === 'ref' ? (r.source_ref || '').trim() : '',
        const_value: r.source_mode === 'ref' ? '' : (r.const_value ?? '')
      })),
      output_vars: atomicOutputRows.value.map((r) => ({
        key: r.key,
        type: r.type || 'STRING',
        description: r.description || ''
      })),
      system_prompt: atomicSystemPrompt.value || DEFAULT_GENERATE_SQL_PROMPT,
      context_vars: atomicContextRows.value
        .map((r) => ({
          name: (r.name || '').trim(),
          source_mode: r.source_mode === 'const' ? 'const' : 'ref',
          source_ref: r.source_mode === 'ref' ? (r.source_ref || '').trim() : '',
          const_value: r.source_mode === 'const' ? (r.const_value ?? '') : ''
        }))
    }
  })
}

function onAtomicCapabilityChange() {
  atomicInputRows.value = normalizeAtomicInputRows(atomicDraft.capability, atomicInputRows.value)
  if (atomicDraft.capability === 'generate-sql') {
    if (!atomicSystemPrompt.value) atomicSystemPrompt.value = DEFAULT_GENERATE_SQL_PROMPT
    atomicContextRows.value = normalizeAtomicContextRows(atomicContextRows.value)
    atomicPromptCollapse.value = ['prompt']
  }
  commitAtomicConfig()
}

function onLabFeaturesConstObjUpdate(v) {
  labFeaturesConstObj.value = v && typeof v === 'object' && !Array.isArray(v) ? v : {}
  scheduleLabFeaturesCommit()
}

function scheduleLabFeaturesCommit() {
  if (labFeaturesCommitTimer) clearTimeout(labFeaturesCommitTimer)
  const id = selectedNodeId.value
  labFeaturesCommitTimer = setTimeout(() => {
    labFeaturesCommitTimer = null
    if (!id || selectedNodeId.value !== id) return
    commitLabConfig()
  }, 280)
}

function commitApiConfig() {
  const prev = selectedNode.value?.data?.api_config || {}
  updateSelectedNodeData({
    api_config: {
      ...prev,
      method: apiDraft.method,
      base_url: apiDraft.base_url || '',
      path: apiDraft.path || '',
      timeout: apiDraft.timeout,
      headers: apiDraft.headers.filter(row => row.key.trim()).map(row => ({ ...row, key: row.key.trim() })),
      query: apiDraft.query.filter(row => row.key.trim()).map(row => ({ ...row, key: row.key.trim() })),
      body_template: apiDraft.body_template
    }
  })
}

function commitApiOutputVars() {
  const prev = selectedNode.value?.data?.api_config || {}
  updateSelectedNodeData({
    api_config: {
      ...prev,
      output_vars: apiOutputRows.value
        .map((r) => ({ name: (r.name || '').trim(), json_path: (r.json_path || '').trim() }))
    }
  })
}

function addApiOutputRow() {
  apiOutputRows.value.push(normalizeApiOutputRow({ name: '', json_path: '' }))
}

function removeApiOutputRow(idx) {
  apiOutputRows.value.splice(idx, 1)
  commitApiOutputVars()
}

function commitSelectorConfig() {
  const rows = selectorCaseRows.value
  if (!rows.length) return
  updateSelectedNodeData({
    selector_config: {
      cases: rows.map((c) => ({
        id: (c.id || '').trim() || `case-${Date.now()}`,
        relation: c.relation || 'AND',
        conditions: (c.conditions || []).map((x) => ({
          ref: (x.ref || '').trim(),
          op: x.op || 'eq',
          value: ['empty', 'not_empty'].includes(x.op) ? '' : (x.value != null ? String(x.value) : '')
        }))
      }))
    }
  })
}

function addSelectorCase() {
  selectorCaseRows.value.push({
    id: `case-${Date.now()}`,
    conditions: [{ ref: '', op: 'starts_with', value: '' }]
  })
  commitSelectorConfig()
}

function removeSelectorCase(idx) {
  if (selectorCaseRows.value.length <= 1) {
    ElMessage.warning('至少保留一个 IF 分支')
    return
  }
  const removed = selectorCaseRows.value[idx]
  edges.value = edges.value.filter(edge => !(edge.source === selectedNodeId.value && edge.sourceHandle === removed.id))
  selectorCaseRows.value.splice(idx, 1)
  commitSelectorConfig()
}

function addSelectorCondition(caseIdx) {
  const row = selectorCaseRows.value[caseIdx]
  if (!row) return
  if (!row.conditions) row.conditions = []
  row.conditions.push({ ref: '', op: 'eq', value: '' })
  commitSelectorConfig()
}

function removeSelectorCondition(caseIdx, condIdx) {
  const row = selectorCaseRows.value[caseIdx]
  const conds = row?.conditions || []
  if (conds.length <= 1) {
    ElMessage.warning('每个分支至少保留一条条件')
    return
  }
  conds.splice(condIdx, 1)
  commitSelectorConfig()
}

let idSeq = 0
let edgeSeq = 0

function bumpSeqFromGraph(nodeList, edgeList) {
  let maxN = 0
  for (const n of nodeList) {
    const m = /^wf-n-\d+-(\d+)$/.exec(n.id)
    if (m) maxN = Math.max(maxN, Number(m[1]))
  }
  idSeq = maxN
  let maxE = 0
  for (const e of edgeList) {
    const m = /^e-\d+-(\d+)$/.exec(e.id)
    if (m) maxE = Math.max(maxE, Number(m[1]))
  }
  edgeSeq = maxE
}

function scheduleDebouncedSave() {
  if (workflowReadonly.value) return
  if (suppressSave.value || autosavePaused.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    persistWorkflow()
  }, SAVE_DEBOUNCE_MS)
}

let activeSave = null
async function persistWorkflow() {
  if (workflowReadonly.value || suppressSave.value) return true
  if (activeSave) return activeSave
  activeSave = (async () => {
    savingWorkflow.value = true
    try {
      let recoveries = 0
      while (hasUnsavedChanges.value) {
        const snapshot = cloneState()
        if (sameWorkflow(snapshot, lastSavedSnapshot.value)) {
          hasUnsavedChanges.value = false
          break
        }
        let data
        try {
          data = await agentAppApi.putWorkflow(Number(props.appId), Number(props.versionId), {
            ...snapshot,
            expected_rev: workflowRev.value,
            undo_stack: JSON.parse(JSON.stringify({ states: history.value.slice(-MAX_HISTORY), index: historyIndex.value }))
          })
        } catch (e) {
          if (!(e.status === 409 || e.code === 'DUPLICATE') || recoveries >= 2) throw e
          recoveries += 1
          const latest = await agentAppApi.getWorkflow(Number(props.appId), Number(props.versionId))
          // A previous request may have committed while its acknowledgement was lost.
          // In that case, retain any newer local edits instead of merging against them.
          if (!sameWorkflow(latest.workflow, snapshot)) {
            const local = cloneState()
            const merged = mergeWorkflows(lastSavedSnapshot.value, local, latest.workflow)
            if (merged.conflicts.length) throw e
            if (!sameWorkflow(merged.workflow, local)) {
              const selectedData = graph => graph.nodes.find(node => node.id === selectedNodeId.value)?.data
              const refreshInspector = !sameWorkflow(
                { nodes: [{ id: 'selected', data: selectedData(local) }] },
                { nodes: [{ id: 'selected', data: selectedData(merged.workflow) }] }
              )
              // A focused field may contain a draft not committed to the graph
              // yet. Its blur handler will schedule the save with that draft.
              if (refreshInspector && document.activeElement instanceof HTMLElement && document.activeElement.closest('.agent-workflow-inspector')) return false
              restoreState(merged.workflow)
              ensureGraphMeta()
              initHistory()
              bumpSeqFromGraph(nodes.value, edges.value)
              if (refreshInspector) syncSelectionAfterHistory()
            }
          }
          workflowRev.value = latest.workflow_rev
          lastSavedSnapshot.value = workflowSnapshot(latest.workflow)
          hasUnsavedChanges.value = !sameWorkflow(lastSavedSnapshot.value, cloneState())
          continue
        }
        workflowRev.value = data.workflow_rev
        lastSavedSnapshot.value = workflowSnapshot(data.workflow || snapshot)
        // Edits made during the request must be saved in the next revision.
        hasUnsavedChanges.value = !sameWorkflow(lastSavedSnapshot.value, cloneState())
        recoveries = 0
      }
      autosavePaused.value = false
      return true
    } catch (e) {
      hasUnsavedChanges.value = true
      if (e.status === 409 || e.code === 'DUPLICATE') {
        if (!autosavePaused.value) ElMessage.warning('同一配置已被其他页面修改，本地修改已保留。请核对后再保存。')
        autosavePaused.value = true
      } else {
        ElMessage.error(e.message || '画布保存失败，本地修改已保留')
      }
      return false
    } finally {
      savingWorkflow.value = false
    }
  })()
  try { return await activeSave } finally { activeSave = null }
}

async function saveNow() {
  if (workflowReadonly.value) return true
  // Commit focused editors before collecting the graph; covers textarea and JSON editors.
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
  await nextTick()
  if (labFeaturesCommitTimer) {
    clearTimeout(labFeaturesCommitTimer)
    labFeaturesCommitTimer = null
    if (inspectorKind.value === 'lab') commitLabConfig()
  }
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  autosavePaused.value = false
  return persistWorkflow()
}

onBeforeRouteLeave(async () => await saveNow())
onBeforeRouteUpdate(async () => await saveNow())
function warnBeforeUnload(event) {
  if (!hasUnsavedChanges.value && !savingWorkflow.value) return
  event.preventDefault()
  event.returnValue = ''
}

async function loadWorkflowFromServer() {
  const id = Number(props.appId)
  const vid = Number(props.versionId)
  const wf = await agentAppApi.getWorkflow(id, vid)
  applyWorkflowResponse(wf)
}

function applyWorkflowResponse(wf) {
  workflowRev.value = wf.workflow_rev ?? 0
  autosavePaused.value = false
  const hasGraph =
    wf.workflow &&
    Array.isArray(wf.workflow.nodes) &&
    (wf.workflow.nodes.length > 0 || (Array.isArray(wf.workflow.edges) && wf.workflow.edges.length > 0))
  if (hasGraph) {
    nodes.value = JSON.parse(JSON.stringify(wf.workflow.nodes || []))
    edges.value = normalizeEdgeList(JSON.parse(JSON.stringify(wf.workflow.edges || [])))
  } else {
    nodes.value = JSON.parse(JSON.stringify(DEFAULT_NODES))
    edges.value = normalizeEdgeList(JSON.parse(JSON.stringify(DEFAULT_EDGES)))
  }
  ensureGraphMeta()
  edges.value = applyBranchEdgeColors(nodes.value, edges.value)
  if (wf.undo_stack?.states?.length) {
    const states = wf.undo_stack.states.map(s => workflowSnapshot({ nodes: s.nodes, edges: applyBranchEdgeColors(s.nodes, normalizeEdgeList(s.edges)) }))
    let idx = Math.min(wf.undo_stack.index, states.length - 1)
    idx = Math.max(0, idx)
    // Redis history can lag a database save. The current graph is authoritative.
    if (sameWorkflow(states[idx], cloneState())) {
      history.value = states
      historyIndex.value = idx
    } else {
      initHistory()
    }
  } else {
    initHistory()
  }
  bumpSeqFromGraph(nodes.value, edges.value)
  lastSavedSnapshot.value = workflowSnapshot(wf.workflow || cloneState())
  hasUnsavedChanges.value = false
  requestViewportFit()
}

function genEdgeId() {
  edgeSeq += 1
  return `e-${Date.now()}-${edgeSeq}`
}

function genNodeId() {
  idSeq += 1
  return `wf-n-${Date.now()}-${idSeq}`
}

function nodeTypeForKind(kind) {
  return kind === 'selector' ? 'wfSelector' : 'wfCard'
}

function insertNodeOnEdge(edgeId, kind) {
  if (workflowReadonly.value) return
  if (kind === 'output') { ElMessage.warning('输出节点应放在分支末端，请从末端节点后添加'); return }
  flushPendingLabConfig()
  const edge = edges.value.find((e) => e.id === edgeId)
  if (!edge) return
  const s = nodes.value.find((n) => n.id === edge.source)
  const t = nodes.value.find((n) => n.id === edge.target)
  if (!s || !t) return
  const label = PALETTE.find((p) => p.kind === kind)?.label || kind
  const nid = genNodeId()
  const nx = (s.position.x + t.position.x) / 2
  const ny = (s.position.y + t.position.y) / 2
  const newNode = {
    id: nid,
    type: nodeTypeForKind(kind),
    position: { x: nx, y: ny },
    data: buildNewNodeData(kind, label)
  }
  const srcEdge = { id: genEdgeId(), source: edge.source, target: nid, type: 'wfPlus' }
  if (edge.sourceHandle != null && edge.sourceHandle !== '') {
    srcEdge.sourceHandle = edge.sourceHandle
  }
  edges.value = edges.value
    .filter((e) => e.id !== edgeId)
    .concat([srcEdge, { id: genEdgeId(), source: nid, target: edge.target, type: 'wfPlus', ...(kind === 'selector' ? { sourceHandle: 'else' } : {}) }])
  nodes.value = [...nodes.value, newNode]
  pushHistory()
  selectedNodeId.value = nid
  requestViewportFit([nid])
}

function addNodeAfter(nodeId, kind) {
  if (workflowReadonly.value) return
  flushPendingLabConfig()
  const node = nodes.value.find((n) => n.id === nodeId)
  if (!node) return
  const label = PALETTE.find((p) => p.kind === kind)?.label || kind
  const nid = genNodeId()
  const hasOutgoing = edges.value.some((e) => e.source === nodeId)
  let nx = node.position.x + 400
  let ny = node.position.y
  if (hasOutgoing) {
    nx = node.position.x + 260
    ny = node.position.y + 132
  }
  const newNode = {
    id: nid,
    type: nodeTypeForKind(kind),
    position: { x: nx, y: ny },
    data: buildNewNodeData(kind, label)
  }
  nodes.value = [...nodes.value, newNode]
  edges.value = [
    ...edges.value,
    { id: genEdgeId(), source: nodeId, target: nid, type: 'wfPlus' }
  ]
  pushHistory()
  selectedNodeId.value = nid
  requestViewportFit([nid])
}

function duplicateNode(nodeId) {
  if (workflowReadonly.value) return
  const node = nodes.value.find((n) => n.id === nodeId)
  if (!node || node.data.kind === 'start' || node.data.kind === 'userInput') return
  const nid = genNodeId()
  const kind = node.data.kind
  const newData = JSON.parse(JSON.stringify(node.data))
  newData.label = allocateNodeLabel(`${newData.label || KIND_LABEL[kind] || kind}_副本`)
  const copy = {
    ...node,
    id: nid,
    type: nodeTypeForKind(kind),
    position: { x: node.position.x + 56, y: node.position.y + 56 },
    data: newData
  }
  nodes.value = [...nodes.value, copy]
  ElMessage.success('已复制节点，可拖拽或自行连线')
  pushHistory()
  selectedNodeId.value = nid
  requestViewportFit([nid])
}

function deleteNode(nodeId) {
  if (workflowReadonly.value) return
  const node = nodes.value.find(n => n.id === nodeId)
  if (node?.data?.kind === 'start') {
    ElMessage.warning('「开始」节点不可删除')
    return
  }
  if (node?.data?.kind === 'userInput') {
    ElMessage.warning('「用户输入」为流程入口，暂不可删除')
    return
  }
  nodes.value = nodes.value.filter((n) => n.id !== nodeId)
  edges.value = edges.value.filter((e) => e.source !== nodeId && e.target !== nodeId)
  if (selectedNodeId.value === nodeId) selectedNodeId.value = null
  pushHistory()
}

function deleteEdge(edgeId) {
  if (workflowReadonly.value) return
  const before = edges.value.length
  edges.value = edges.value.filter((e) => e.id !== edgeId)
  if (edges.value.length !== before) pushHistory()
}

function deleteEdgeByLink(sourceId, targetId) {
  if (workflowReadonly.value) return
  const before = edges.value.length
  edges.value = edges.value.filter((e) => !(e.source === sourceId && e.target === targetId))
  if (edges.value.length !== before) pushHistory()
}

provide('wfGraph', {
  palette: paletteForMenu,
  readonly: workflowReadonly,
  insertNodeOnEdge,
  addNodeAfter,
  duplicateNode,
  deleteNode,
  deleteEdge,
  deleteEdgeByLink
})

function addPaletteNode(kind) {
  if (workflowReadonly.value) return
  flushPendingLabConfig()
  const label = PALETTE.find((p) => p.kind === kind)?.label || kind
  const id = genNodeId()
  const x = 560 + (idSeq % 3) * 80
  const y = 120 + Math.floor(idSeq / 3) * 140
  nodes.value = [
    ...nodes.value,
    {
      id,
      type: nodeTypeForKind(kind),
      position: { x, y },
      data: buildNewNodeData(kind, label)
    }
  ]
  pushHistory()
  selectedNodeId.value = id
  requestViewportFit([id])
}

function onConnect(params) {
  if (workflowReadonly.value) return
  if (params.source === params.target) { ElMessage.warning('节点不能连接到自己'); return }
  if (collectUpstreamNodeIds(params.source).has(params.target)) { ElMessage.warning('此连线会产生循环，请检查连接方向'); return }
  const src = nodes.value.find((n) => n.id === params.source)
  if (src?.data?.kind === 'selector' && (params.sourceHandle == null || params.sourceHandle === '')) {
    ElMessage.warning('请从选择器右侧具体分支（IF / ELIF / ELSE）的圆点拉出连线')
    return
  }
  const e = {
    ...params,
    id: genEdgeId(),
    type: 'wfPlus'
  }
  edges.value = addEdge(e, edges.value)
  pushHistory()
}

function onNodeDragStop() {
  if (workflowReadonly.value) return
  let changed = false
  const GRID = 12
  const list = nodes.value.map((n) => ({ ...n, position: { ...n.position } }))
  for (let i = 0; i < list.length; i += 1) {
    const a = list[i]
    // 对齐网格（避免小数漂移）
    const gx = Math.round((a.position.x || 0) / GRID) * GRID
    const gy = Math.round((a.position.y || 0) / GRID) * GRID
    if (gx !== a.position.x || gy !== a.position.y) {
      a.position.x = gx
      a.position.y = gy
      changed = true
    }
  }
  if (changed) {
    nodes.value = list
  }
  pushHistory()
}

function onSelectionDragStop() {
  onNodeDragStop()
}

function flushPendingLabConfig() {
  if (!labFeaturesCommitTimer) return
  clearTimeout(labFeaturesCommitTimer)
  labFeaturesCommitTimer = null
  if (inspectorKind.value === 'lab') commitLabConfig()
}

function onNodeClick({ node }) {
  flushPendingLabConfig()
  selectedNodeId.value = node.id
}

function onPaneClick() {
  flushPendingLabConfig()
  selectedNodeId.value = null
}

function clearSelection() {
  flushPendingLabConfig()
  selectedNodeId.value = null
}

function goBack() {
  router.push({ name: 'AgentAppVersions', params: { appId: props.appId } })
}

function goToDebugMode() {
  router.push({
    name: 'AgentWorkflowDebug',
    params: { appId: props.appId, versionId: props.versionId },
    query: { ...route.query }
  })
}

async function publishWorkflow() {
  if (!await saveNow()) return
  const invalid = nodes.value.find(node => nodeConfigurationIssues(node).length)
  if (invalid) {
    selectedNodeId.value = invalid.id
    ElMessage.warning(`请先完善「${invalid.data?.label || invalid.id}」配置`)
    return
  }
  try {
    await ElMessageBox.confirm('发布后此版本将只读；如需继续修改，可创建新版本。', '发布工作流', { type: 'warning', confirmButtonText: '发布', cancelButtonText: '取消' })
    await agentAppApi.publishVersion(Number(props.appId), Number(props.versionId))
    app.value = await agentAppApi.getAgentApp(Number(props.appId))
    ElMessage.success('工作流已发布')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '发布失败')
  }
}

async function load() {
  const id = Number(props.appId)
  if (Number.isNaN(id)) {
    ElMessage.warning('无效的应用 ID')
    router.replace('/agent-platform/agents')
    return
  }
  loading.value = true
  suppressSave.value = true
  try {
    try {
      const providers = await getModelProviders()
      modelProviders.value = Array.isArray(providers) ? providers : []
    } catch {
      modelProviders.value = []
    }
    try {
      const knowledgeBases = await knowledgeBaseApi.getKnowledgeBaseList({ skip: 0, limit: 500 })
      knowledgeBaseOptions.value = (Array.isArray(knowledgeBases) ? knowledgeBases : []).map((kb) => ({
        value: String(kb.id),
        label: kb.name ? `${kb.name} (#${kb.id})` : `知识库 #${kb.id}`
      }))
    } catch {
      knowledgeBaseOptions.value = []
    }
    const data = await agentAppApi.getAgentApp(id)
    app.value = data
    const vid = Number(props.versionId)
    const v = data.versions?.find((x) => x.id === vid)
    if (!v) {
      ElMessage.warning('未找到该版本')
      router.replace({ name: 'AgentAppVersions', params: { appId: props.appId } })
      return
    }
    await loadWorkflowFromServer()
    const qro = route.query.readonly === '1' || route.query.readonly === 'true'
    const pageLabel =
      v.status !== 'designing' || qro ? '工作流详情' : '工作流编排'
    document.title = `${data.name} · ${v.name} · ${pageLabel} - AI4BI`
  } catch (e) {
    ElMessage.error(e.message || '加载失败')
    router.replace('/agent-platform/agents')
  } finally {
    loading.value = false
    nextTick(() => {
      suppressSave.value = false
    })
  }
}

watch(() => [props.appId, props.versionId], () => { selectedNodeId.value = null; load() })

onMounted(() => {
  window.addEventListener('keydown', onDocKeydown)
  window.addEventListener('beforeunload', warnBeforeUnload)
  if (route.meta?.title) {
    document.title = `${route.meta.title} - AI4BI`
  }
  load()
})

onUnmounted(() => {
  viewportDisposed = true
  if (saveTimer) clearTimeout(saveTimer)
  if (labFeaturesCommitTimer) clearTimeout(labFeaturesCommitTimer)
  window.removeEventListener('keydown', onDocKeydown)
  window.removeEventListener('beforeunload', warnBeforeUnload)
})
</script>

<style scoped>
.wf-atomic-required { color: #b45309; font-size: 11px; }
.workflow-validation { margin-bottom: 12px; }
.workflow-validation ul { padding-left: 18px; margin: 4px 0; }
.agent-workflow-page {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
  background: linear-gradient(180deg, #f4f6f9 0%, #eef1f6 100%);
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

.agent-workflow-top {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px 16px;
  width: 100%;
  min-width: 0;
  min-height: 56px;
  padding: 0 20px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.8) inset;
}

.agent-workflow-top__left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.agent-workflow-pill-tab {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #475467;
  text-decoration: none;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.agent-workflow-top__center {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 4px;
  border-radius: 10px;
  background: rgba(61, 141, 130, 0.08);
  border: 1px solid rgba(61, 141, 130, 0.12);
  gap: 4px;
}

.agent-workflow-pill-tab:hover {
  color: var(--el-color-primary);
  background: rgba(255, 255, 255, 0.7);
}

.agent-workflow-pill-tab.is-active {
  background: #fff;
  color: var(--el-color-primary);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.agent-workflow-top__right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.agent-workflow-toolbar-btn {
  border-radius: 10px;
  font-weight: 600;
}

.agent-workflow-toolbar-btn--minor {
  border-radius: 9px;
  font-weight: 500;
  font-size: 12px;
  padding-left: 10px;
  padding-right: 10px;
  color: #475467;
  border-color: #d8dee8;
  background: #fff;
}

.agent-workflow-toolbar-btn--minor:hover {
  color: #1d2939;
  border-color: #c5cfde;
  background: #f9fafb;
}

.agent-workflow-toolbar-btn--debug {
  border-radius: 10px;
  border-color: rgba(var(--el-color-primary-rgb), 0.42);
  color: var(--el-color-primary);
  background: rgba(var(--el-color-primary-rgb), 0.08);
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.06),
    inset 0 0 0 1px rgba(var(--el-color-primary-rgb), 0.08);
}

.agent-workflow-toolbar-btn--debug:hover {
  background: rgba(var(--el-color-primary-rgb), 0.14);
  border-color: rgba(var(--el-color-primary-rgb), 0.56);
}

.agent-workflow-toolbar-btn--save {
  border-radius: 10px;
  min-width: 84px;
  color: #175cd3;
  border-color: #b2ccff;
  background: #eff4ff;
}

.agent-workflow-toolbar-btn--save:hover {
  border-color: #84adff;
  background: #dfeaff;
}

.agent-workflow-publish {
  border-radius: 10px;
  font-weight: 600;
  padding-left: 18px;
  padding-right: 18px;
  box-shadow: 0 1px 2px rgba(var(--el-color-primary-rgb), 0.35);
}

.agent-workflow-back {
  flex-shrink: 0;
}

.agent-workflow-title-block {
  min-width: 0;
}

.agent-workflow-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #101828;
  letter-spacing: -0.02em;
  line-height: 1.3;
}

.agent-workflow-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
  color: #667085;
  margin-top: 2px;
}

.agent-workflow-status-tag {
  margin-left: 4px;
}

.agent-workflow-body {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  width: 100%;
  max-width: 100%;
  display: flex;
  align-items: stretch;
}

.agent-workflow-canvas-wrap {
  flex: 1 1 0%;
  min-width: 0;
  min-height: 0;
  position: relative;
  z-index: 0;
  overflow: hidden;
  border-radius: 0 0 0 12px;
  background: #f8faf9;
}

.agent-workflow-canvas-wrap :deep(.vue-flow) {
  width: 100%;
  height: 100%;
  min-height: 320px;
}

/* 小地图缩在画布左下，避免与右侧配置栏视觉混淆 */
.agent-workflow-canvas-wrap :deep(.vue-flow__panel.bottom.left) {
  margin: 12px;
}

.agent-workflow-canvas-wrap :deep(.vue-flow__panel.bottom.right) {
  margin: 12px;
}

.agent-workflow-inspector:not(.is-idle) {
  flex-shrink: 0;
  position: relative;
  z-index: 4;
  background: #fff;
  border-left: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: -12px 0 32px rgba(15, 23, 42, 0.06);
  display: flex;
  flex-direction: column;
  padding: 18px 20px;
  gap: 12px;
  overflow-y: auto;
  overflow-x: hidden;
  pointer-events: auto;
}

.agent-workflow-inspector.is-idle {
  justify-content: center;
  align-items: stretch;
}

.agent-workflow-inspector__idle {
  text-align: center;
  padding: 24px 8px 32px;
}

.agent-workflow-inspector__idle-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 14px;
  border-radius: 14px;
  background: linear-gradient(145deg, rgba(var(--el-color-primary-rgb), 0.12), rgba(var(--el-color-primary-rgb), 0.05));
  color: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.agent-workflow-inspector__idle-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 700;
  color: #101828;
}

.agent-workflow-inspector__idle-text {
  margin: 0 0 8px;
  font-size: 13px;
  color: #667085;
  line-height: 1.55;
}

.agent-workflow-inspector__idle-hint {
  margin: 0;
  font-size: 12px;
  color: #98a2b3;
  line-height: 1.5;
}

.agent-workflow-readonly-tag {
  margin-right: 4px;
  align-self: center;
}

.agent-workflow-inspector__fieldset {
  border: none;
  margin: 0;
  padding: 0;
  min-width: 0;
}

.agent-workflow-inspector__head {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-workflow-inspector__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-workflow-inspector__icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(var(--el-color-primary-rgb), 0.1);
  color: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.agent-workflow-inspector__title {
  flex: 1;
  font-size: 16px;
  font-weight: 700;
  color: #101828;
}

.agent-workflow-inspector__title-input {
  flex: 1;
  min-width: 0;
}

.agent-workflow-inspector__title-input :deep(.el-input__wrapper) {
  box-shadow: none;
  padding-left: 0;
  background: transparent;
}

.agent-workflow-inspector__title-input :deep(.el-input__inner) {
  font-size: 16px;
  font-weight: 700;
  color: #101828;
}

.agent-workflow-inspector__desc :deep(.el-textarea__inner) {
  font-size: 13px;
}

.agent-workflow-inspector__settings {
  flex: 1;
  min-height: 0;
  padding-top: 12px;
  overflow: auto;
}

.agent-workflow-inspector__placeholder {
  font-size: 13px;
  color: #475467;
  line-height: 1.6;
}

.agent-workflow-inspector__hint {
  margin: 8px 0 0;
  color: #98a2b3;
  font-size: 12px;
}

.agent-workflow-insp-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.agent-workflow-insp-field.agent-workflow-insp-inline {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 12px;
}

.agent-workflow-insp-field--flush {
  margin-bottom: 0;
}

.agent-workflow-script-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #98a2b3;
  line-height: 1.5;
}

.agent-workflow-script-hint code {
  font-size: 11px;
  padding: 0 4px;
  border-radius: 4px;
  background: #f2f4f7;
  color: #344054;
}

.agent-workflow-insp-label {
  font-size: 12px;
  font-weight: 600;
  color: #475467;
}

.agent-workflow-insp-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.agent-workflow-insp-toolbar-title {
  font-size: 13px;
  font-weight: 600;
  color: #101828;
}

.agent-workflow-insp-rowline {
  display: grid;
  grid-template-columns: 1fr 1fr auto auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.agent-workflow-userinput-collapse {
  margin-top: 4px;
  border: none;
  --el-collapse-header-height: 40px;
}

.agent-workflow-userinput-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  color: #101828;
}

.agent-workflow-userinput-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.user-input-params {
  margin-top: 4px;
}

.user-input-params__row {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid #e6eaf2;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%);
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}

.user-input-params__row:last-of-type {
  margin-bottom: 8px;
}

.user-input-params__line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.user-input-params__line-label {
  width: 42px;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: #667085;
}

.user-input-params__line-note {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: #667085;
}

.user-input-params__line :deep(.el-input),
.user-input-params__line :deep(.el-select),
.user-input-params__line :deep(.el-cascader) {
  flex: 1;
  min-width: 0;
}

.user-input-params__remove {
  margin-left: auto;
  color: #b42318;
}

.user-input-params__source-pair {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px;
}

.user-input-params__source-mode {
  width: 120px;
}

.user-input-params__cascader {
  flex: 1;
  min-width: 0;
}

.user-input-params__type-row {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-input-params__type-row :deep(.el-checkbox) {
  margin-left: 4px;
  flex-shrink: 0;
}

.user-input-params--agent .user-input-params__line--action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.user-input-params--agent .user-input-params__header {
  display: grid;
  grid-template-columns: 15% 30% 15% 10% 20% 10%;
  gap: 0;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #667085;
  background: #f9fafb;
  border-radius: 8px 8px 0 0;
  box-sizing: border-box;
}

.user-input-params--agent .user-input-params__header > * {
  padding: 0 8px;
  white-space: nowrap;
}

.user-input-params--agent .user-input-params__row {
  display: grid;
  grid-template-columns: 15% 30% 15% 10% 20% 10%;
  gap: 0;
  padding: 10px 12px;
  border-bottom: 1px solid #e6eaf2;
  box-sizing: border-box;
}

.user-input-params--agent .user-input-params__row > * {
  padding: 0 8px;
}

.user-input-params--agent.user-input-params--output .user-input-params__header {
  display: grid;
  grid-template-columns: 30% 20% 50%;
  gap: 0;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #667085;
  background: #f9fafb;
  border-radius: 8px 8px 0 0;
  box-sizing: border-box;
}

.user-input-params--agent.user-input-params--output .user-input-params__header > * {
  padding: 0 8px;
}

.user-input-params--agent.user-input-params--output .user-input-params__row {
  display: grid;
  grid-template-columns: 30% 20% 50%;
  gap: 0;
  padding: 10px 12px;
  border-bottom: 1px solid #e6eaf2;
  box-sizing: border-box;
}

.user-input-params--agent.user-input-params--output .user-input-params__row > * {
  padding: 0 8px;
}

.user-input-params--agent .user-input-params__line--action {
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-input-params--agent .param-name {
  font-weight: 500;
  color: #1f2937;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-input-params--agent .param-type {
  font-size: 12px;
  color: #667085;
  white-space: nowrap;
}

.user-input-params--agent .param-default {
  font-size: 12px;
  color: #9ca3af;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-input-params--agent .param-desc {
  font-size: 12px;
  color: #667085;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-input-params--agent .user-input-params__line--name,
.user-input-params--agent .user-input-params__line--source {
  display: flex;
  align-items: center;
  width: 100%;
  box-sizing: border-box;
}

.user-input-params--agent .user-input-params__source-pair {
  display: flex;
  gap: 4px;
  width: 100%;
}

.user-input-params__source-mode {
  width: 100%;
}

.user-input-params__add {
  margin-top: 4px;
}

.wf-atomic-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.wf-atomic-capability {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e6eaf2;
  border-radius: 10px;
  background: #fff;
}

.wf-atomic-capability__label,
.wf-atomic-section__head,
.wf-atomic-row__key,
.wf-atomic-compact__label {
  font-size: 12px;
  font-weight: 700;
  color: #344054;
}

.wf-atomic-capability__select {
  width: 100%;
}

.wf-atomic-section {
  border: 1px solid #e6eaf2;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
  overflow: hidden;
}

.wf-atomic-section__head {
  display: flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  border-bottom: 1px solid #eef2f7;
  background: #f8fafc;
}

.wf-atomic-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px 12px;
  padding: 12px;
}

.wf-atomic-row {
  min-width: 0;
}

.wf-atomic-row--wide {
  grid-column: 1 / -1;
}

.wf-atomic-row__meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  margin-bottom: 6px;
}

.wf-atomic-row__key {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wf-atomic-row__type {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: #98a2b3;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.wf-atomic-row__body {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.wf-atomic-mode,
.wf-atomic-value {
  width: 100%;
  min-width: 0;
}

.wf-atomic-advanced {
  border: 1px solid #e6eaf2;
  border-radius: 12px;
  overflow: hidden;
  --el-collapse-header-height: 36px;
}

.wf-atomic-advanced :deep(.el-collapse-item__header) {
  padding: 0 12px;
  font-size: 12px;
  font-weight: 700;
  color: #344054;
  background: #f8fafc;
}

.wf-atomic-advanced :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.wf-atomic-advanced :deep(.el-collapse-item__content) {
  padding: 12px;
}

.wf-atomic-compact-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.wf-atomic-compact {
  min-width: 0;
}

.wf-atomic-compact__label {
  display: block;
  margin-bottom: 5px;
  white-space: nowrap;
}

.wf-atomic-compact__input {
  width: 100%;
}

.wf-atomic-output-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px 12px;
}

.wf-atomic-section--outputs {
  background: #fff;
}

.agent-workflow-code :deep(.el-textarea__inner) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

/* —— 侧栏：LLM / 选择器 与画布节点语义色统一的配置面板 —— */
.wf-insp-panel {
  margin: 0;
  padding: 14px 14px 16px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  min-width: 100%;
  width: 100%;
}

.wf-insp-panel--llm {
  --insp-accent: #6366f1;
  --insp-accent-deep: #4338ca;
  --insp-soft: rgba(99, 102, 241, 0.1);
  --insp-surface: linear-gradient(165deg, rgba(238, 242, 255, 0.92) 0%, #ffffff 58%);
  background: var(--insp-surface);
}

.wf-insp-panel--selector {
  --insp-accent: #3b82f6;
  --insp-accent-deep: #1d4ed8;
  --insp-soft: rgba(59, 130, 246, 0.11);
  --insp-surface: linear-gradient(168deg, rgba(239, 246, 255, 0.94) 0%, #ffffff 55%);
  background: var(--insp-surface);
}

.wf-insp-callout {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 12px;
  margin-bottom: 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(15, 23, 42, 0.06);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.9) inset;
}

.wf-insp-callout--compact {
  margin-bottom: 12px;
}

.wf-insp-callout__icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: var(--insp-accent-deep);
  background: var(--insp-soft);
}

.wf-insp-panel--selector .wf-insp-callout__icon {
  margin-top: 2px;
}

.wf-insp-callout__body {
  flex: 1;
  min-width: 0;
}

.wf-insp-callout__title {
  display: block;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #101828;
  margin-bottom: 4px;
}

.wf-insp-callout__text {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: #667085;
}

.wf-insp-callout__text code {
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #f2f4f7;
  color: #344054;
}

.wf-insp-collapse {
  margin-top: 0;
}

.wf-insp-panel .wf-insp-collapse :deep(.el-collapse-item__header) {
  border-radius: 10px;
  padding-left: 13px;
  margin-bottom: 2px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(15, 23, 42, 0.05);
  border-left: 3px solid var(--insp-accent);
  font-size: 13px;
}

.wf-insp-panel .wf-insp-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
}

.wf-insp-panel .wf-insp-collapse :deep(.el-collapse-item__content) {
  padding: 10px 4px 6px;
}

.wf-insp-field {
  margin-bottom: 14px;
  display: flex;
  flex-direction: column;
}

.wf-insp-field--grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.wf-insp-field--grid2 .wf-inp-subfield {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wf-insp-field--grid2 .wf-inp-subfield:only-child {
  grid-column: 1 / -1;
}

.wf-insp-field--flush {
  margin-bottom: 0;
}

.wf-insp-field__label {
  font-size: 12px;
  font-weight: 600;
  color: #475467;
}

.wf-insp-field__hint {
  margin: -2px 0 0;
  font-size: 11px;
  color: #98a2b3;
  line-height: 1.4;
}

.wf-insp-field--grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.wf-insp-field--switch-row {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.wf-insp-field--switch-row .wf-insp-field__label {
  margin: 0;
}

.wf-inp-subfield {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.wf-inp-subfield__control {
  width: 100%;
}

.wf-insp-prompt-textarea :deep(.el-textarea__inner) {
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
}

/* 选择器：分支卡片 */
.wf-insp-branch-card {
  margin-bottom: 12px;
  padding: 12px 12px 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(15, 23, 42, 0.07);
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
}

.wf-inp-conds-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.05);
  border: 1px solid rgba(59, 130, 246, 0.1);
}

.wf-inp-conds-relation-label {
  font-size: 11px;
  font-weight: 600;
  color: #475467;
  flex-shrink: 0;
}

.wf-inp-conds-header :deep(.el-radio-button__inner) {
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 6px;
}

.wf-insp-branch-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.wf-insp-branch-card__title-block {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.wf-inp-branch-name {
  font-size: 13px;
  font-weight: 600;
  color: #101828;
}

.wf-inp-branch-pill {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  padding: 3px 8px;
  border-radius: 6px;
  color: var(--insp-accent-deep);
  background: var(--insp-soft);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.wf-inp-branch-pill--else {
  color: #475467;
  background: rgba(15, 23, 42, 0.06);
}

.wf-inp-text-danger {
  flex-shrink: 0;
}

.wf-inp-conds__legend {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(76px, 0.42fr) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
  padding: 0 2px;
  font-size: 11px;
  font-weight: 600;
  color: #98a2b3;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.wf-inp-conds__legend-actions {
  width: 44px;
}

.wf-inp-conds__row {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(76px, 0.42fr) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.wf-inp-conds__row:last-of-type {
  margin-bottom: 4px;
}

.wf-inp-conds__cell {
  min-width: 0;
}

.wf-inp-conds__val-wrap {
  min-height: 28px;
  display: flex;
  align-items: center;
}

.wf-inp-conds__val-wrap :deep(.el-input) {
  width: 100%;
}

.wf-inp-conds__na {
  font-size: 12px;
  color: #98a2b3;
  padding-left: 2px;
}

.wf-inp-conds__rm {
  padding: 4px 6px !important;
  flex-shrink: 0;
}

.wf-inp-add-cond {
  margin-top: 2px;
}

.wf-inp-add-branch {
  width: 100%;
  margin: 4px 0 14px;
  border-radius: 10px;
  font-weight: 600;
  border-style: dashed;
  border-color: rgba(59, 130, 246, 0.45);
  background: rgba(59, 130, 246, 0.06);
}

.wf-inp-add-branch:hover {
  background: rgba(59, 130, 246, 0.1);
}

.wf-inp-else-card {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.65);
  border: 1px dashed rgba(15, 23, 42, 0.12);
}

.wf-inp-else-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.wf-inp-else-card__sub {
  font-size: 12px;
  font-weight: 600;
  color: #667085;
}

.wf-inp-else-card__desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #98a2b3;
}
</style>

<style>
/* 下拉挂到 body，需非 scoped */
.wf-picker-block {
  margin-top: 2px;
}

.wf-picker-add {
  width: 100%;
  justify-content: center;
  border-radius: 12px;
  padding: 12px 14px;
  border: 1px dashed rgba(var(--el-color-primary-rgb), 0.35);
  background: rgba(var(--el-color-primary-rgb), 0.06);
}

.wf-picker-summary {
  border: 2px solid rgba(var(--el-color-primary-rgb), 0.25);
  border-radius: 10px;
  background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%);
  padding: 10px;
  box-shadow: 0 8px 18px rgba(16, 24, 40, 0.05);
  position: relative;
}

.wf-picker-summary::before {
  content: '';
  position: absolute;
  left: 9px;
  top: 9px;
  bottom: 9px;
  width: 3px;
  border-radius: 3px;
  background: rgba(var(--el-color-primary-rgb), 0.55);
}

.wf-picker-summary__main {
  padding-left: 10px;
}

.wf-picker-summary__main {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.wf-picker-summary__title {
  font-weight: 700;
  color: #101828;
  font-size: 13px;
}

.wf-picker-summary__sub {
  font-size: 12px;
  color: #667085;
  line-height: 1.4;
}

.wf-picker-summary__ops {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  align-items: center;
}

.wf-picker-summary__version {
  margin-top: 8px;
}

.wf-picker-summary__version-btn {
  width: 100%;
  border-radius: 8px;
}

.wf-dialog-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  color: #101828;
}

.wf-dialog-search {
  display: flex;
  gap: 10px;
  align-items: center;
  margin: 10px 0 16px;
}

.wf-dialog-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.wf-dialog-grid--agents {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.wf-dialog-grid--labs {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.wf-dialog-loading {
  padding: 18px 0;
  color: #667085;
  text-align: center;
}

.wf-dialog-footer-note {
  color: #98a2b3;
  font-size: 12px;
  margin-right: auto;
}

.wf-version-body {
  padding: 6px 0 4px;
}

.lab-features-editor-wrap {
  border: 1px solid rgba(15, 23, 42, 0.1);
  background: #fcfcfd;
  border-radius: 12px;
  padding: 10px 12px;
  min-width: 0;
}

.wf-pick-card {
  border: 1px solid rgba(16, 24, 40, 0.08);
  background: #fff;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  gap: 10px;
  align-items: flex-start;
  cursor: pointer;
  transition: box-shadow 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.wf-pick-card:hover {
  border-color: rgba(var(--el-color-primary-rgb), 0.35);
  box-shadow: 0 6px 18px rgba(16, 24, 40, 0.07);
  transform: translateY(-1px);
}

.wf-pick-card.is-active {
  border-color: rgba(var(--el-color-primary-rgb), 0.55);
  box-shadow: 0 8px 22px rgba(var(--el-color-primary-rgb), 0.16);
}

.wf-pick-card__left {
  flex-shrink: 0;
}

.wf-pick-card__icon {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: linear-gradient(145deg, rgba(var(--el-color-primary-rgb), 0.18), rgba(var(--el-color-primary-rgb), 0.06));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.wf-pick-card__icon--lab {
  background: linear-gradient(145deg, rgba(16, 185, 129, 0.18), rgba(16, 185, 129, 0.06));
  color: #0f766e;
  font-weight: 800;
}

.wf-pick-card__right {
  flex: 1 1 auto;
  min-width: 0;
}

.wf-pick-card__name {
  font-size: 13px;
  font-weight: 700;
  color: #101828;
  line-height: 1.25;
}

.wf-pick-card__desc {
  margin-top: 6px;
  font-size: 12px;
  color: #667085;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 880px) {
  .wf-dialog-grid {
    grid-template-columns: 1fr;
  }
}

.agent-workflow-node-dropdown.el-popper {
  border-radius: 12px;
  padding: 6px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12);
}

.agent-workflow-node-dropdown .el-dropdown-menu {
  padding: 4px;
}

.agent-workflow-node-dropdown .el-dropdown-menu__item {
  border-radius: 8px;
  padding: 8px 12px;
  font-weight: 600;
}

.agent-workflow-node-menu__row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-workflow-node-menu__icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.agent-workflow-node-menu__icon.is-llm {
  background: rgba(var(--el-color-primary-rgb), 0.12);
  color: var(--el-color-primary);
}
.agent-workflow-node-menu__icon.is-script {
  background: rgba(var(--el-color-primary-rgb), 0.1);
  color: var(--el-color-primary-dark-2, var(--el-color-primary));
}
.agent-workflow-node-menu__icon.is-selector {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
}
.agent-workflow-node-menu__icon.is-agent {
  background: rgba(102, 112, 196, 0.12);
  color: #5c64a8;
}
.agent-workflow-node-menu__icon.is-lab {
  background: rgba(61, 141, 130, 0.12);
  color: #2f7269;
}
.agent-workflow-node-menu__icon.is-externalApi {
  background: rgba(180, 130, 70, 0.12);
  color: #a16207;
}
.agent-workflow-node-menu__icon.is-output {
  background: rgba(194, 65, 92, 0.1);
  color: #b42318;
}
</style>
