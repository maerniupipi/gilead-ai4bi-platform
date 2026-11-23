<template>
  <div v-loading="loading" class="xq-workbench">
    <!-- 顶部导航 -->
    <header class="xq-wb-head">
      <div class="head-crumbs">
        <router-link to="/agent-platform/tools" class="crumb-link">{{ t('crumb.tools') }}</router-link>
        <span class="crumb-sep">/</span>
        <router-link to="/agent-platform/tools/xlsx-qa" class="crumb-link">{{ t('crumb.xlsxQa') }}</router-link>
        <span class="crumb-sep">/</span>
        <span>{{ moduleDetail?.name || '…' }}</span>
      </div>
      <div class="head-actions">
        <el-tag v-if="docStatus" :type="docStatusType" size="small">
          {{ docStatusLabel }}
        </el-tag>
        <el-tag v-if="moduleHasMultiDocs" type="info" size="small">
          {{ allDocuments.length }} files / {{ totalSheetCount }} sheets
        </el-tag>
        <el-button v-if="moduleDetail?.primary_document && !moduleHasMultiDocs" link size="small" @click="onDownload">
          <el-icon><Download /></el-icon>
          {{ t('wb.btn.download') }}
        </el-button>
        <el-button
          size="small"
          :icon="Setting"
          @click="promptsDrawerVisible = true"
        >
          {{ t('wb.btn.settings') }}
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :icon="DocumentCopy"
          :disabled="pptExportDisabled"
          @click="onExportPpt"
        >
          {{ t('wb.btn.exportPpt') }}
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :icon="Download"
          :disabled="pdfExportDisabled"
          :loading="pdfExporting"
          @click="onExportPdf"
        >
          {{ t('wb.btn.exportPdf') }}
        </el-button>
        <!-- 语言切换：点一下在 中 ↔ EN 之间切，持久化到 localStorage，
             切换后 UI 立即刷新；LLM 回答语言由用户问题本身决定，不受这个按钮影响。 -->
        <el-button
          size="small"
          class="lang-toggle"
          :title="t('lang.switch')"
          @click="toggleLang"
        >
          <span class="lang-toggle-text">中 / EN</span>
        </el-button>
      </div>
    </header>

    <div class="xq-wb-body" :class="{ 'hide-right': hideRightPanel }">
      <!-- 左栏：会话列表 -->
      <aside class="xq-wb-side">
        <div class="side-head">
          <span>{{ t('wb.side.conv') }}</span>
          <el-button :disabled="!canAsk || insightStreaming" size="small" :icon="Plus" @click="onNewConversation">{{ t('wb.side.new') }}</el-button>
        </div>
        <div class="conv-list">
          <div
            v-if="insightHistoryVisible"
            class="conv-item conv-item--insight"
            :class="{ 'is-active': insightMode }"
            @click="openInsight"
          >
            <div class="conv-title">{{ t('insight.cardTitle') }}</div>
            <div class="conv-meta">{{ insightHistoryMeta }}</div>
            <span class="conv-insight-mark" :title="insightHistoryTag">
              <span class="conv-insight-mark-dot" />
              {{ insightHistoryTag }}
            </span>
          </div>
          <div
            v-for="c in conversations"
            :key="c.id"
            class="conv-item"
            :class="{ 'is-active': c.id === activeConvId }"
            @click="selectConv(c.id)"
          >
            <div class="conv-title">{{ c.title }}</div>
            <div class="conv-meta">{{ t('wb.side.msgCount', { n: c.message_count }) }}</div>
            <el-icon class="conv-del" @click.stop="onDeleteConv(c)"><Delete /></el-icon>
          </div>
          <div v-if="!conversations.length" class="conv-empty">
            {{ t('wb.side.empty') }}
          </div>
        </div>
      </aside>

      <!-- 中间：对话区 -->
      <section class="xq-wb-main">
        <!-- 解析进度页 -->
        <div v-if="parsing" class="parse-progress-wrap">
          <div class="parse-progress-icon">
            <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="14" y="20" width="52" height="46" rx="4" fill="#e8f5e9" stroke="#10b981" stroke-width="2"/>
              <rect x="22" y="30" width="36" height="4" rx="2" fill="#10b981" opacity="0.5"/>
              <rect x="22" y="38" width="28" height="4" rx="2" fill="#10b981" opacity="0.35"/>
              <rect x="22" y="46" width="32" height="4" rx="2" fill="#10b981" opacity="0.25"/>
              <circle cx="40" cy="22" r="10" fill="#fff" stroke="#10b981" stroke-width="2"/>
              <path d="M36 22l3 3 5-5" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="parse-progress-title">{{ t('wb.parsing.title') }}</div>
          <div class="parse-progress-desc">{{ t('wb.parsing.desc') }}</div>
          <div class="parse-progress-bar-wrap">
            <div class="parse-progress-bar">
              <div
                class="parse-progress-fill"
                :class="{ 'is-done': parseProgress >= 100 }"
                :style="{ width: parseProgress + '%' }"
              />
            </div>
            <span class="parse-progress-pct">{{ parseProgress }}%</span>
          </div>
        </div>

        <!-- 无文件 / 其他不可问状态 -->
        <div v-else-if="!canAsk" class="no-file-hint">
          <el-empty :description="noFileHint">
            <el-button
              v-if="!moduleDetail?.primary_document"
              type="primary"
              :icon="UploadFilled"
              @click="triggerUpload"
            >
              {{ t('wb.noFile.upload') }}
            </el-button>
          </el-empty>
        </div>

        <template v-else>
        <!-- Sheet 范围选择器（多 Sheet 时显示） -->
        <div v-if="totalSheetCount > 1" class="sheet-scope">
          <span class="sheet-scope-label">{{ t('wb.sheetScope.title') }}:</span>
          <el-tag
            v-for="sh in allSheets"
            :key="sh.id"
            :type="isSheetActive(sh.id) ? 'primary' : 'info'"
            :effect="isSheetActive(sh.id) ? 'dark' : 'plain'"
            size="small"
            class="sheet-scope-chip"
            :class="{ 'is-active': isSheetActive(sh.id) }"
            @click="toggleActiveSheet(sh.id)"
          >
            {{ sh._doc.file_name }} / {{ sh.sheet_name }}
          </el-tag>
          <el-button
            v-if="activeSheetIds !== null"
            link
            size="small"
            @click="resetActiveSheets"
          >
            {{ t('wb.sheetScope.all') }}
          </el-button>
        </div>

        <div ref="scrollerRef" class="messages-scroller" :class="{ 'messages-scroller--insight': insightMode }">
          <template v-if="insightMode">
            <XlsxQaInsightReport
              :module-id="moduleId"
              @close="onInsightClose"
              @streaming="insightStreaming = $event"
              @done="onInsightDone"
              @export-ppt="onExportInsightPpt"
              @export-pdf="onExportPdf"
            />
          </template>
          <template v-else>
          <!-- Stage 0 Think Card -->
          <transition name="el-fade-in">
            <div v-if="moduleThinkContent && isStreaming" class="think-card">
              <div class="think-card-head">
                <span class="think-card-title">{{ t('wb.think.title') }}</span>
                <el-button
                  v-if="thinkCollapsed"
                  link
                  size="small"
                  @click="thinkCollapsed = false"
                >
                  {{ t('wb.think.autoCollapse') }}
                </el-button>
              </div>
              <div v-show="!thinkCollapsed" class="think-card-body">
                {{ moduleThinkContent }}
              </div>
            </div>
          </transition>

          <div v-if="!messages.length && !isStreaming" class="welcome">
            <button
              v-if="showInsightWelcomeCard"
              type="button"
              class="insight-entry-card"
              @click="openInsight"
            >
              <span class="insight-entry-badge">{{ t('insight.badge') }}</span>
              <div class="insight-entry-title">{{ t('insight.cardTitle') }}</div>
              <p class="insight-entry-desc">{{ t('insight.cardDesc') }}</p>
              <span class="insight-entry-cta">{{ t('insight.cardCta') }}</span>
            </button>
            <div class="welcome-title">{{ t('wb.welcome.title') }}</div>
            <div class="welcome-desc">
              {{ t('wb.welcome.desc') }}
            </div>
            <div class="welcome-samples">
              <el-button
                v-for="q in sampleQuestions"
                :key="q"
                size="small"
                round
                plain
                @click="askQuick(q)"
              >
                {{ q }}
              </el-button>
            </div>
          </div>

          <XlsxQaMessageBubble
            v-for="m in messages"
            :key="m._localKey || m.id"
            :message="m"
            :streaming="m._streaming"
            :selectable="m.role === 'assistant' && typeof m.id === 'number' && m.status !== 'failed'"
            :selected="selectedMessageIds.includes(m.id)"
            :show-sql="showSql"
            @follow-up="askQuick"
            @toggle-select="toggleSelectMessage"
          />
          </template>
        </div>
        </template>

        <!-- 输入区（深度洞察全屏模式下隐藏） -->
        <div v-if="!insightMode" class="composer" :class="{ 'is-disabled': !canAsk || isStreaming || insightStreaming }">
          <el-input
            v-model="questionInput"
            type="textarea"
            :rows="2"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="!canAsk || isStreaming || insightStreaming"
            :placeholder="canAsk ? t('wb.composer.placeholder') : t('wb.composer.disabled')"
            resize="none"
            @keydown.enter.exact.prevent="onSubmit"
          />
          <div class="composer-foot">
            <el-button
              type="primary"
              :disabled="!canAsk || !questionInput.trim()"
              :loading="isStreaming"
              :icon="Promotion"
              @click="onSubmit"
            >
              {{ t('wb.composer.send') }}
            </el-button>
          </div>
        </div>
      </section>

      <!-- 右栏：文档 / 字段 / 预览 -->
      <aside v-if="!hideRightPanel" class="xq-wb-right">
        <!-- 全局文件输入（始终挂载，供各处 triggerUpload 使用） -->
        <input
          ref="fileInputRef"
          type="file"
          accept=".xlsx,.xlsm"
          style="display:none"
          @change="onFileChange"
        />
        <!-- 无文档：上传区 -->
        <div v-if="!hasDocuments && !moduleDetail?.primary_document" class="right-upload">
          <div class="right-title">{{ t('wb.right.uploadTitle') }}</div>
          <div class="right-desc">{{ t('wb.right.uploadSheetDesc') }}</div>
          <el-button
            type="primary"
            :loading="uploading || parsing"
            :icon="UploadFilled"
            style="width:100%"
            :disabled="parsing"
            @click="triggerUpload"
          >
            <template v-if="uploading">{{ t('wb.right.uploadingBtn') }}</template>
            <template v-else-if="parsing">{{ t('wb.right.parsingBtn') }}</template>
            <template v-else>{{ t('wb.right.uploadSheetBtn') }}</template>
          </el-button>
          <div v-if="uploading" class="upload-tip">{{ t('wb.right.uploadTip') }}</div>
          <div v-if="parsing" class="upload-tip">{{ t('wb.right.parseTip') }}</div>
        </div>

        <!-- 旧版单文档（向后兼容） -->
        <div v-else-if="moduleDetail?.primary_document && !moduleHasMultiDocs" class="doc-panel">
          <div class="right-title">
            <span>{{ t('wb.right.dataFile') }}</span>
            <el-button link size="small" @click="onDeleteDoc" style="color:#ef4444">
              {{ t('common.delete') }}
            </el-button>
          </div>
          <div class="doc-info">
            <div class="doc-name">
              <el-icon><Grid /></el-icon>
              {{ moduleDetail.primary_document.file_name }}
            </div>
            <div class="doc-meta">
              <span>Sheet: {{ moduleDetail.primary_document.sheet_name || 'Sheet1' }}</span>
              <span>{{ t('wb.right.rows', { n: moduleDetail.primary_document.total_rows }) }}</span>
              <span>{{ t('wb.right.cols', { n: moduleDetail.primary_document.total_columns }) }}</span>
            </div>
          </div>

          <el-tabs v-model="rightTab" class="right-tabs">
            <el-tab-pane :label="t('wb.right.tab.columns')" name="columns">
              <div class="column-list">
                <div
                  v-for="col in moduleDetail.primary_document.columns"
                  :key="col.column_name"
                  class="column-row"
                >
                  <div class="column-main">
                    <div class="column-raw">{{ col.raw_header || col.column_name }}</div>
                    <div class="column-sub">
                      <code>{{ col.column_name }}</code>
                      <el-tag size="small" type="info">{{ col.column_type }}</el-tag>
                    </div>
                  </div>
                  <div v-if="col.sample?.length" class="column-samples" :title="col.sample.join(', ')">
                    e.g. {{ col.sample.slice(0, 3).join(' / ') }}
                  </div>
                </div>
              </div>
            </el-tab-pane>
            <el-tab-pane :label="t('wb.right.tab.understanding')" name="understanding">
              <div class="understanding-pane">
                <div class="understanding-toolbar">
                  <el-tag v-if="moduleDetail.primary_document.understanding_md" type="success" size="small">{{ t('wb.right.und.generated') }}</el-tag>
                  <el-tag v-else size="small" type="info">{{ t('wb.right.und.notGenerated') }}</el-tag>
                  <el-button
                    size="small"
                    plain
                    :loading="understandingLoading"
                    @click="regenerateUnderstanding"
                  >
                    {{ moduleDetail.primary_document.understanding_md ? t('wb.right.und.regen') : t('wb.right.und.gen') }}
                  </el-button>
                  <span class="understanding-hint">{{ t('wb.right.und.hint') }}</span>
                </div>
                <div
                  v-if="moduleDetail.primary_document.understanding_md"
                  class="understanding-md markdown-body"
                  v-html="renderedUnderstanding"
                />
                <el-empty v-else :description="t('wb.right.und.empty')" :image-size="64" />
              </div>
            </el-tab-pane>
            <el-tab-pane :label="t('wb.right.tab.preview')" name="preview" lazy>
              <div v-loading="previewLoading" class="preview-pane">
                <el-button size="small" plain @click="loadPreview">{{ t('wb.right.preview.refresh') }}</el-button>
                <el-table
                  v-if="preview?.columns?.length"
                  :data="previewRows"
                  size="small"
                  border
                  stripe
                  max-height="320"
                  style="margin-top:8px"
                >
                  <el-table-column
                    v-for="c in preview.columns"
                    :key="c"
                    :prop="c"
                    :label="c"
                    show-overflow-tooltip
                    min-width="120"
                  />
                </el-table>
                <div v-if="preview?.total_rows" class="preview-meta">
                  {{ t('wb.right.preview.meta', { shown: previewRows.length, got: preview.total_rows, total: moduleDetail.primary_document.total_rows }) }}
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>

        <!-- 多文档面板 -->
        <div v-else class="doc-panel multi-doc-panel">
          <el-tabs v-model="multiDocTab" class="multi-doc-tabs">
            <el-tab-pane :label="t('wb.right.multiFile', { n: allDocuments.length })" name="files">
              <div class="multi-doc-tab-head">
                <el-button
                  v-if="canUploadMore"
                  size="small"
                  plain
                  :icon="Plus"
                  @click="triggerUpload"
                  :disabled="uploading || parsing"
                >
                  {{ t('wb.right.uploadSheet') }}
                </el-button>
              </div>

              <div
                v-for="doc in allDocuments"
                :key="doc.id"
                class="doc-card"
              >
                <div class="doc-card-head" @click="toggleDocExpand(doc.id)">
                  <el-icon class="doc-expand-icon">
                    <ArrowRight v-if="!expandedDocIds.has(doc.id)" />
                    <ArrowDown v-else />
                  </el-icon>
                  <div class="doc-card-info">
                    <div class="doc-card-name">
                      <el-icon><Grid /></el-icon>
                      <span class="doc-card-filename">{{ doc.file_name }}</span>
                      <el-tag v-if="doc.status !== 'ready'" :type="doc.status === 'failed' ? 'danger' : 'warning'" size="small">
                        {{ t(`status.${doc.status}`) }}
                      </el-tag>
                    </div>
                    <div class="doc-card-meta">
                      <span>{{ t('wb.right.docSheetCount', { n: doc.sheet_count || 0 }) }}</span>
                      <span>{{ t('wb.right.rows', { n: doc.total_rows }) }}</span>
                      <span>{{ t('wb.right.cols', { n: doc.total_columns }) }}</span>
                    </div>
                  </div>
                  <el-button link size="small" @click.stop="onDeleteDocById(doc.id)" style="color:#ef4444">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>

                <!-- 展开的 Sheet 列表 -->
                <div v-show="expandedDocIds.has(doc.id)" class="doc-sheet-list">
                  <div
                    v-for="sh in doc.sheets || []"
                    :key="sh.id"
                    class="sheet-item"
                  >
                    <div
                      class="sheet-row"
                      :class="{ 'is-expanded': expandedSheetIds.has(sh.id) }"
                      @click="sh.status === 'ready' && toggleSheetExpand(sh.id)"
                    >
                      <el-icon class="sheet-expand-icon" v-if="sh.status === 'ready'">
                        <ArrowRight v-if="!expandedSheetIds.has(sh.id)" />
                        <ArrowDown v-else />
                      </el-icon>
                      <div class="sheet-row-main">
                        <div class="sheet-row-name">
                          <el-tag
                            :type="sh.status === 'ready' ? 'success' : sh.status === 'failed' ? 'danger' : 'warning'"
                            size="small"
                            effect="plain"
                          >
                            {{ t(`status.${sh.status}`) }}
                          </el-tag>
                          <span class="sheet-name-text">{{ sh.sheet_name }}</span>
                        </div>
                        <div class="sheet-row-meta">
                          <span>{{ sh.total_rows || 0 }} 行</span>
                          <span>{{ (sh.columns || []).length }} 列</span>
                        </div>
                      </div>
                      <el-button
                        v-if="sh.status !== 'parsing'"
                        link
                        size="small"
                        :icon="Refresh"
                        :loading="sheetRegenLoading === sh.id"
                        @click.stop="regenerateSheet(sh)"
                        :title="sh.understanding_md ? t('wb.right.und.regen') : t('wb.right.und.gen')"
                      />
                    </div>

                    <!-- Sheet 详情面板 -->
                    <div v-if="expandedSheetIds.has(sh.id)" class="sheet-detail-panel">
                      <el-tabs
                        :model-value="getSheetDetailTab(sh.id)"
                        @update:model-value="setSheetDetailTab(sh.id, $event)"
                        class="sheet-detail-tabs"
                        size="small"
                      >
                        <el-tab-pane :label="t('wb.right.tab.columns')" name="columns">
                          <div class="column-list column-list-compact">
                            <div
                              v-for="col in sh.columns || []"
                              :key="col.column_name"
                              class="column-row"
                            >
                              <div class="column-main">
                                <div class="column-raw">{{ col.raw_header || col.column_name }}</div>
                                <div class="column-sub">
                                  <code>{{ col.column_name }}</code>
                                  <el-tag size="small" type="info">{{ col.column_type }}</el-tag>
                                </div>
                              </div>
                              <div v-if="col.sample?.length" class="column-samples" :title="col.sample.join(', ')">
                                e.g. {{ col.sample.slice(0, 3).join(' / ') }}
                              </div>
                            </div>
                          </div>
                        </el-tab-pane>
                        <el-tab-pane :label="t('wb.right.tab.understanding')" name="understanding">
                          <div class="understanding-pane">
                            <!-- 编辑态 -->
                            <div v-if="editingSheetId === sh.id" class="understanding-edit">
                              <el-input
                                v-model="editingSheetMd"
                                type="textarea"
                                :rows="12"
                                resize="vertical"
                                placeholder="输入表理解内容..."
                              />
                              <div class="understanding-edit-actions">
                                <el-button size="small" @click="cancelEditSheet">{{ t('common.cancel') }}</el-button>
                                <el-button size="small" type="primary" @click="saveEditSheet(sh)">{{ t('common.confirm') }}</el-button>
                              </div>
                            </div>
                            <!-- 展示态 -->
                            <template v-else>
                              <div class="understanding-toolbar">
                                <el-tag v-if="sh.understanding_md" type="success" size="small">{{ t('wb.right.und.generated') }}</el-tag>
                                <el-tag v-else size="small" type="info">{{ t('wb.right.und.notGenerated') }}</el-tag>
                                <el-button
                                  v-if="sh.understanding_md"
                                  size="small"
                                  plain
                                  @click="startEditSheet(sh)"
                                >
                                  {{ t('common.edit') }}
                                </el-button>
                                <el-button
                                  size="small"
                                  plain
                                  :loading="sheetRegenLoading === sh.id"
                                  @click="regenerateSheet(sh)"
                                >
                                  {{ sh.understanding_md ? t('wb.right.und.regen') : t('wb.right.und.gen') }}
                                </el-button>
                              </div>
                              <div
                                v-if="sh.understanding_md"
                                class="understanding-md markdown-body"
                                v-html="renderSimpleMarkdown(sh.understanding_md)"
                              />
                              <el-empty v-else :description="t('wb.right.und.empty')" :image-size="48" />
                            </template>
                          </div>
                        </el-tab-pane>
                        <el-tab-pane :label="t('wb.right.tab.preview')" name="preview" lazy>
                          <div v-loading="sheetPreviewLoading[sh.id]" class="preview-pane">
                            <el-button size="small" plain @click="loadSheetPreview(sh.id)">{{ t('wb.right.preview.refresh') }}</el-button>
                            <el-table
                              v-if="sheetPreview[sh.id]?.columns?.length"
                              :data="getSheetPreviewRows(sh.id)"
                              size="small"
                              border
                              stripe
                              max-height="240"
                              style="margin-top:8px"
                            >
                              <el-table-column
                                v-for="c in sheetPreview[sh.id].columns"
                                :key="c"
                                :prop="c"
                                :label="c"
                                show-overflow-tooltip
                                min-width="100"
                              />
                            </el-table>
                            <div v-if="sheetPreview[sh.id]?.total_rows" class="preview-meta">
                              {{ t('wb.right.preview.meta', { shown: getSheetPreviewRows(sh.id).length, got: sheetPreview[sh.id].total_rows, total: sh.total_rows }) }}
                            </div>
                          </div>
                        </el-tab-pane>
                      </el-tabs>
                    </div>
                  </div>
                  <div v-if="!doc.sheets?.length" class="sheet-empty">
                    {{ t('wb.right.und.notGenerated') }}
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <!-- 文件理解 tab -->
            <el-tab-pane
              v-if="moduleDetail?.module_understanding_md"
              label="文件理解"
              name="understanding"
            >
              <div class="file-understanding-pane">
                <div class="file-understanding-toolbar">
                  <el-button
                    size="small"
                    plain
                    :icon="Refresh"
                    :loading="moduleSummaryLoading"
                    @click="regenerateModuleSummaryDoc"
                  >
                    {{ t('wb.right.und.regen') }}
                  </el-button>
                </div>
                <div class="understanding-md markdown-body" v-html="renderSimpleMarkdown(moduleDetail.module_understanding_md)" />
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </aside>

      <!-- 上传 Sheet 选择对话框 -->
      <el-dialog
        v-model="sheetSelectVisible"
        :title="t('wb.right.uploadSheetSelect')"
        width="420px"
        :close-on-click-modal="false"
      >
        <div class="sheet-select-list">
          <div
            v-for="sh in pendingSheetNames"
            :key="sh.index"
            class="sheet-select-row"
            :class="{ 'is-selected': selectedSheetIndices.includes(sh.index) }"
            @click="toggleSheetSelect(sh.index)"
          >
            <el-checkbox :model-value="selectedSheetIndices.includes(sh.index)" />
            <span class="sheet-select-name">{{ sh.name }}</span>
            <span class="sheet-select-idx">(Sheet #{{ sh.index + 1 }})</span>
          </div>
          <div v-if="!pendingSheetNames.length" class="sheet-select-empty">
            未检测到有效工作表
          </div>
        </div>
        <div class="sheet-select-foot">
          <span class="sheet-select-hint">{{ t('wb.right.uploadSheetSelected', { n: selectedSheetIndices.length }) }}</span>
          <div>
            <el-button size="small" link @click="selectedSheetIndices = pendingSheetNames.map(s => s.index)">
              {{ t('wb.right.uploadSheetAll') }}
            </el-button>
            <el-button size="small" link @click="selectedSheetIndices = []">
              {{ t('wb.right.uploadSheetNone') }}
            </el-button>
          </div>
        </div>
        <template #footer>
          <el-button @click="sheetSelectVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button
            type="primary"
            :disabled="!selectedSheetIndices.length"
            @click="confirmUploadWithSheets"
          >
            {{ t('common.confirm') }}
          </el-button>
        </template>
      </el-dialog>
    </div>

    <!-- 高级设置（提示词） -->
    <XlsxQaPromptsDrawer
      v-model="promptsDrawerVisible"
      :module-id="moduleId"
      :show-sql="showSql"
      :hide-right-panel="hideRightPanel"
      @update:showSql="onShowSqlChange"
      @update:hideRightPanel="onHideRightPanelChange"
    />

    <!-- 导出 PPT -->
    <XlsxQaExportPptDialog
      v-model="exportDialogVisible"
      :conversation-id="activeConvId"
      :module-id="moduleId"
      :messages="messages"
      :initial-selected-ids="selectedMessageIds"
    />

    <!-- 洞察报告导出 PPT -->
    <XlsxQaExportPptDialog
      v-model="insightExportDialogVisible"
      :insight-mode="true"
      :module-id="moduleId"
      :export-fn="insightPptExportFn"
    />

    <!-- 知识卡片 -->
    <transition name="el-fade-in">
      <div v-if="knowledgeCard.visible" class="knowledge-card">
        <div class="knowledge-card-header">
          <span>{{ t('knowledge.title') }}</span>
          <el-button link size="small" @click="onKnowledgeReject">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
        <div class="knowledge-card-desc">{{ t('knowledge.desc') }}</div>
        <div class="knowledge-items">
          <div
            v-for="(item, idx) in knowledgeCard.items"
            :key="idx"
            class="knowledge-item"
          >
            <div class="ki-row">
              <div class="ki-field">
                <span class="ki-label">{{ t('knowledge.alias') }}</span>
                <el-tag size="small" type="info">{{ item.alias }}</el-tag>
              </div>
              <div class="ki-field">
                <span class="ki-label">{{ t('knowledge.mapsTo') }}</span>
                <span class="ki-value">{{ item.maps_to }}</span>
              </div>
              <div v-if="item.column_hint" class="ki-field">
                <span class="ki-label">{{ t('knowledge.column') }}</span>
                <code>{{ item.column_hint }}</code>
              </div>
            </div>
            <el-input
              v-model="item.description"
              :placeholder="t('knowledge.descPlaceholder')"
              :maxlength="100"
              show-word-limit
              size="small"
              style="margin-top: 6px"
            />
          </div>
        </div>
        <div class="knowledge-card-actions">
          <el-button size="small" @click="onKnowledgeReject">{{ t('knowledge.reject') }}</el-button>
          <el-button
            type="primary"
            size="small"
            :loading="knowledgeCard.loading"
            @click="onKnowledgeAccept"
          >
            {{ t('knowledge.accept') }}
          </el-button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  Delete,
  Download,
  UploadFilled,
  Grid,
  InfoFilled,
  Promotion,
  Setting,
  DocumentCopy,
  Close,
  ArrowDown,
  ArrowRight,
  Refresh,
} from '@element-plus/icons-vue'

import {
  getXlsxQaModule,
  uploadXlsxQaDocument,
  deleteXlsxQaDocument,
  getXlsxQaDocumentDownloadUrl,
  previewXlsxQaDocument,
  previewXlsxQaSheet,
  regenerateXlsxQaUnderstanding,
  regenerateSheetUnderstanding,
  updateSheetUnderstanding,
  regenerateModuleSummary,
  listXlsxQaConversations,
  createXlsxQaConversation,
  deleteXlsxQaConversation,
  listXlsxQaMessages,
  updateConversationSheets,
  appendXlsxQaKnowledge,
  exportXlsxQaConversationPdf,
  exportXlsxQaInsightPdf,
  exportXlsxQaInsightPptAsync,
} from '../../../api/xlsxQa'
import { askXlsxQaStream, fetchInsightReport } from '../../../utils/xlsxQaSse'
import { renderSimpleMarkdown } from '../../../utils/markdown'
import XlsxQaInsightReport from '../../../components/xlsx-qa/XlsxQaInsightReport.vue'
import XlsxQaMessageBubble from '../../../components/xlsx-qa/XlsxQaMessageBubble.vue'
import XlsxQaPromptsDrawer from '../../../components/xlsx-qa/XlsxQaPromptsDrawer.vue'
import XlsxQaExportPptDialog from '../../../components/xlsx-qa/XlsxQaExportPptDialog.vue'
import { useXqI18n } from '../../../utils/xlsxQaI18n'

const { t, lang, toggleLang } = useXqI18n()

const route = useRoute()
const router = useRouter()

const moduleId = computed(() => Number(route.params.moduleId))

const loading = ref(false)
const moduleDetail = ref(null)
const conversations = ref([])
const activeConvId = ref(null)
const messages = ref([])

const uploading = ref(false)
const uploadProgress = ref(0)
const parsing = ref(false)       // 上传完成、后台解析中（轮询 understanding_md）
const parseProgress = ref(0)     // 0-100，假进度条
const fileInputRef = ref(null)
let _parsePoller = null          // setInterval handle（轮询）
let _progressTimer = null        // setInterval handle（进度条）

const questionInput = ref('')
const isStreaming = ref(false)
const insightMode = ref(false)
const insightStreaming = ref(false)
const insightReportInfo = ref(null)
const abortCtrl = ref(null)
const scrollerRef = ref(null)

const rightTab = ref('columns')
const preview = ref(null)
const previewLoading = ref(false)
const understandingLoading = ref(false)

const renderedUnderstanding = computed(() =>
  renderSimpleMarkdown(moduleDetail.value?.primary_document?.understanding_md || '')
)

async function regenerateUnderstanding() {
  const doc = moduleDetail.value?.primary_document
  if (!doc) return
  understandingLoading.value = true
  try {
    const info = await regenerateXlsxQaUnderstanding(moduleId.value, doc.id)
    moduleDetail.value.primary_document = info
    ElMessage.success(t('wb.right.und.success'))
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('common.failed'))
  } finally {
    understandingLoading.value = false
  }
}

const promptsDrawerVisible = ref(false)
const exportDialogVisible = ref(false)
const insightExportDialogVisible = ref(false)
const selectedMessageIds = ref([])
const pdfExporting = ref(false)

// 知识卡片状态
const knowledgeCard = ref({
  visible: false,
  loading: false,
  items: [],
})

// 多 Sheet 状态
const activeSheetIds = ref(null)         // null = 全选（默认）；[] = 空（禁止）；[id,...] = 指定
const expandedDocIds = ref(new Set())    // 右侧栏展开的文件 id 集合
const expandedSheetIds = ref(new Set())  // 右侧栏展开的 sheet id 集合
const multiDocTab = ref('files')         // 多文档模式 tab: 'files' | 'understanding'
const moduleThinkContent = ref('')       // Stage 0 模块规划 think 内容
const moduleThinkRelevantIds = ref([])   // Stage 0 推荐的 Sheet ID

// Sheet 详情 tab 和编辑状态
const sheetDetailTab = ref({})           // { [sheetId]: 'columns' | 'understanding' | 'preview' }
const sheetPreview = ref({})             // { [sheetId]: previewData }
const sheetPreviewLoading = ref({})      // { [sheetId]: bool }
const editingSheetId = ref(null)
const editingSheetMd = ref('')

// 上传 Sheet 选择对话框
const sheetSelectVisible = ref(false)
const pendingUploadFile = ref(null)
const pendingSheetNames = ref([])        // [{ index, name }]
const selectedSheetIndices = ref([])     // 用户勾选的 index 列表

// Think card 折叠
const thinkCollapsed = ref(false)

// Sheet 重生成 & 模块汇总 loading
const sheetRegenLoading = ref(null)     // sheet id or null
const moduleSummaryLoading = ref(false)

function onKnowledgeReject() {
  knowledgeCard.value.visible = false
  knowledgeCard.value.items = []
}

async function onKnowledgeAccept() {
  const mod = moduleDetail.value
  if (!mod?.id || !knowledgeCard.value.items.length) return
  knowledgeCard.value.loading = true
  try {
    const res = await appendXlsxQaKnowledge({
      module_id: mod.id,
      knowledge_items: knowledgeCard.value.items.map((item) => ({
        alias: item.alias || '',
        maps_to: item.maps_to || '',
        column_hint: item.column_hint || null,
        description: (item.description || '').slice(0, 100),
        sheet_id: item.sheet_id || null,
      })),
    })
    // 更新右侧表理解展示
    if (res.sheet_id != null && moduleHasMultiDocs.value) {
      // 多文档：更新对应的 sheet
      for (const doc of allDocuments.value) {
        const sheet = (doc.sheets || []).find(s => s.id === res.sheet_id)
        if (sheet) {
          sheet.understanding_md = res.understanding_md
          break
        }
      }
    } else if (mod.primary_document) {
      mod.primary_document.understanding_md = res.understanding_md
    }
    ElMessage.success(t('knowledge.accepted'))
    knowledgeCard.value.visible = false
    knowledgeCard.value.items = []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('common.failed'))
  } finally {
    knowledgeCard.value.loading = false
  }
}

// SQL 显示控制：per-module，存 localStorage
function _sqlKey() { return `xlsx-qa-show-sql-${moduleId.value}` }
const showSql = ref(false)
function loadShowSqlPref() {
  try {
    showSql.value = localStorage.getItem(_sqlKey()) === 'true'
  } catch { showSql.value = false }
}
function onShowSqlChange(v) {
  showSql.value = v
  try { localStorage.setItem(_sqlKey(), v ? 'true' : 'false') } catch { /* ignore */ }
}

function _rightPanelKey() { return `xlsx-qa-hide-right-${moduleId.value}` }
const hideRightPanel = ref(false)
function loadHideRightPanelPref() {
  try {
    hideRightPanel.value = localStorage.getItem(_rightPanelKey()) === 'true'
  } catch { hideRightPanel.value = false }
}
function onHideRightPanelChange(v) {
  hideRightPanel.value = v
  try { localStorage.setItem(_rightPanelKey(), v ? 'true' : 'false') } catch { /* ignore */ }
}

const hasAnyAssistant = computed(() =>
  messages.value.some((m) => m.role === 'assistant' && typeof m.id === 'number' && m.status !== 'failed')
)
const pptExportDisabled = computed(() => {
  if (insightStreaming.value || isStreaming.value) return true
  if (insightMode.value) return !canAsk.value || insightReportInfo.value?.status !== 'done'
  return !hasAnyAssistant.value
})
const pdfExportDisabled = computed(() => {
  if (pdfExporting.value || insightStreaming.value || isStreaming.value) return true
  if (insightMode.value) return !canAsk.value
  return !activeConvId.value || !hasAnyAssistant.value
})
const activeConvTitle = computed(
  () => conversations.value.find((c) => c.id === activeConvId.value)?.title || ''
)

function toggleSelectMessage(id, val) {
  const has = selectedMessageIds.value.includes(id)
  const want = typeof val === 'boolean' ? val : !has
  if (want && !has) selectedMessageIds.value.push(id)
  if (!want && has) selectedMessageIds.value = selectedMessageIds.value.filter((x) => x !== id)
}

// 多文档辅助
const allDocuments = computed(() => moduleDetail.value?.documents || [])
const hasDocuments = computed(() => allDocuments.value.length > 0)
const allSheets = computed(() => {
  const sheets = []
  for (const doc of allDocuments.value) {
    if (doc.sheets?.length) {
      for (const sh of doc.sheets) sheets.push({ ...sh, _doc: doc })
    }
  }
  return sheets
})
const totalSheetCount = computed(() => allSheets.value.length)
const canUploadMore = computed(() => allDocuments.value.length < 5)

// 向后兼容：仍支持 primary_document（单文件旧模块）
const moduleHasMultiDocs = computed(() => allDocuments.value.length > 0)

const docStatus = computed(() => {
  if (moduleHasMultiDocs.value) {
    // 多文档模式：取第一个非 ready 的状态
    for (const doc of allDocuments.value) {
      if (doc.status === 'failed') return 'failed'
      if (doc.status === 'parsing') return 'parsing'
    }
    return moduleDetail.value?.all_sheets_ready ? 'ready' : 'parsing'
  }
  return moduleDetail.value?.primary_document?.status
})
const docStatusLabel = computed(() => {
  const s = docStatus.value
  return s ? t(`status.${s}`) : ''
})
const docStatusType = computed(() => (
  { ready: 'success', failed: 'danger', parsing: 'warning', pending: 'warning' }[docStatus.value] || 'info'
))

// parsing=true 时表示后台表理解还在生成，此时禁止提问（数据还不完整）
const canAsk = computed(() => docStatus.value === 'ready' && !parsing.value)
const noFileHint = computed(() => {
  if (!hasDocuments.value && !moduleDetail.value?.primary_document) return t('wb.noFile.hint')
  if (parsing.value) return t('wb.noFile.parsing')
  if (docStatus.value !== 'ready') return t('wb.noFile.status', { s: docStatusLabel.value })
  return ''
})

function openInsight() {
  if (!canAsk.value || isStreaming.value || insightStreaming.value) return
  if (!insightReportInfo.value) {
    insightReportInfo.value = {
      status: 'generating',
      dimensions: [],
      updated_at: new Date().toISOString(),
    }
  }
  insightMode.value = true
}

/** 已成功生成过洞察报告时不再展示欢迎区的「一键生成洞察」推荐卡片（仍可从左侧洞察会话进入） */
const showInsightWelcomeCard = computed(() => insightReportInfo.value?.status !== 'done')

const insightHistoryVisible = computed(() => {
  const s = insightReportInfo.value?.status
  return ['done', 'generating', 'failed'].includes(s)
})
const insightHistoryTag = computed(() => {
  const s = insightReportInfo.value?.status
  if (s === 'done') return '洞察'
  if (s === 'generating') return '生成中'
  if (s === 'failed') return '失败'
  return '洞察'
})
const insightHistoryMeta = computed(() => {
  const info = insightReportInfo.value || {}
  const n = Array.isArray(info.dimensions) ? info.dimensions.length : 0
  const t1 = n ? `${n} 个维度` : '数据洞察报告'
  const t2 = info.updated_at ? formatShortDate(info.updated_at) : ''
  return t2 ? `${t1} · ${t2}` : t1
})

async function loadInsightReportInfo() {
  try {
    const data = await fetchInsightReport(moduleId.value)
    insightReportInfo.value = data?.exists ? data : null
  } catch {
    insightReportInfo.value = null
  }
}

function onInsightDone() {
  insightStreaming.value = false
  loadInsightReportInfo()
}

function onInsightClose() {
  insightMode.value = false
  insightStreaming.value = false
  loadInsightReportInfo()
}

function formatShortDate(s) {
  const d = new Date(s)
  if (isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 后端给的是一批中文 fallback；前端在这里按当前 UI 语言切一套；
// 若表解析时 LLM 已经基于表头语言生成了 suggested_questions，优先用那份。
const fallbackQuestions = computed(() => [
  t('wb.fallback.q1'),
  t('wb.fallback.q2'),
  t('wb.fallback.q3'),
])
const sampleQuestions = computed(() => {
  // 多文档模式：取第一个 sheet 的 suggested_questions
  if (moduleHasMultiDocs.value) {
    for (const doc of allDocuments.value) {
      for (const sh of (doc.sheets || [])) {
        if (sh.suggested_questions?.length) return sh.suggested_questions
      }
    }
  }
  const list = moduleDetail.value?.primary_document?.suggested_questions
  return Array.isArray(list) && list.length ? list : fallbackQuestions.value
})

const previewRows = computed(() => {
  if (!preview.value?.columns?.length) return []
  const cols = preview.value.columns
  return (preview.value.rows || []).map((r) => {
    const o = {}
    cols.forEach((c, i) => {
      const v = r[i]
      o[c] = v === null || v === undefined ? '' : v
    })
    return o
  })
})

// ------------------- 数据加载 -------------------

async function loadModule() {
  try {
    moduleDetail.value = await getXlsxQaModule(moduleId.value)
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
    router.replace('/agent-platform/tools/xlsx-qa')
  }
}

async function loadConversations() {
  try {
    conversations.value = await listXlsxQaConversations(moduleId.value)
    if (!activeConvId.value && conversations.value.length) {
      activeConvId.value = conversations.value[0].id
    }
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

async function loadMessages(convId) {
  if (!convId) {
    messages.value = []
    return
  }
  try {
    const rows = await listXlsxQaMessages(convId)
    messages.value = rows.map((m) => ({ ...m }))
    moduleThinkContent.value = ''
    moduleThinkRelevantIds.value = []
    thinkCollapsed.value = false
    scrollBottom()
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

function selectConv(id) {
  activeConvId.value = id
  insightMode.value = false
  insightStreaming.value = false
  // 恢复会话的 Sheet 范围
  const conv = conversations.value.find(c => c.id === id)
  if (conv?.active_sheet_ids?.length) {
    activeSheetIds.value = conv.active_sheet_ids
  } else {
    activeSheetIds.value = null
  }
  loadMessages(id)
}

async function onNewConversation() {
  try {
    const conv = await createXlsxQaConversation(moduleId.value)
    conversations.value.unshift({ ...conv })
    skipNextAutoLoad.value = true
    activeConvId.value = conv.id
    messages.value = []
    activeSheetIds.value = null
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

async function onDeleteConv(c) {
  try {
    await ElMessageBox.confirm(t('wb.deleteConv.body', { t: c.title }), t('wb.deleteConv.title'), { type: 'warning' })
  } catch { return }
  try {
    await deleteXlsxQaConversation(c.id)
    conversations.value = conversations.value.filter((x) => x.id !== c.id)
    if (activeConvId.value === c.id) {
      activeConvId.value = conversations.value[0]?.id || null
      await loadMessages(activeConvId.value)
    }
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

// ------------------- 上传 / 下载 / 预览 -------------------

function triggerUpload() {
  fileInputRef.value?.click()
}
async function onFileChange(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  if (!/\.xls[xm]$/i.test(file.name)) {
    ElMessage.error(t('wb.onlyXlsx'))
    return
  }
  uploading.value = true
  uploadProgress.value = 0
  try {
    await uploadXlsxQaDocument(moduleId.value, file, {
      onProgress: (p) => (uploadProgress.value = p)
    })
    ElMessage.success(t('wb.uploadOk'))
    await loadModule()
    // 如果表理解还未生成，启动轮询直到生成完毕
    _startParsePoller()
  } catch (err) {
    ElMessage.error(err.message || t('common.failed'))
  } finally {
    uploading.value = false
    uploadProgress.value = 0
  }
}

function _startParsePoller() {
  // 检查是否需要轮询
  let needsPoll = false
  if (moduleHasMultiDocs.value) {
    // 多文档模式：检查是否有 sheet 还没 ready
    needsPoll = !moduleDetail.value?.all_sheets_ready
  } else {
    const doc = moduleDetail.value?.primary_document
    needsPoll = doc && !doc.understanding_md
  }
  if (!needsPoll) return

  parsing.value = true
  parseProgress.value = 0

  // 假进度：每秒随机 +1% 或 +2%，到 90% 停住
  _progressTimer = setInterval(() => {
    if (parseProgress.value < 90) {
      const step = Math.random() < 0.5 ? 1 : 2
      parseProgress.value = Math.min(90, parseProgress.value + step)
    }
  }, 1000)

  // 轮询真实完成状态
  _parsePoller = setInterval(async () => {
    try {
      const detail = await getXlsxQaModule(moduleId.value)
      moduleDetail.value = detail
      if (moduleHasMultiDocs.value) {
        if (detail?.all_sheets_ready) _finishParseProgress()
      } else {
        if (detail?.primary_document?.understanding_md) _finishParseProgress()
      }
    } catch { /* ignore polling errors */ }
  }, 3000)
}

function _finishParseProgress() {
  // 停进度 timer，跳到 100%，短暂停留后再清理
  if (_progressTimer !== null) {
    clearInterval(_progressTimer)
    _progressTimer = null
  }
  parseProgress.value = 100
  setTimeout(() => {
    parsing.value = false
    parseProgress.value = 0
    if (_parsePoller !== null) {
      clearInterval(_parsePoller)
      _parsePoller = null
    }
  }, 600)
}

function _stopParsePoller() {
  if (_progressTimer !== null) {
    clearInterval(_progressTimer)
    _progressTimer = null
  }
  if (_parsePoller !== null) {
    clearInterval(_parsePoller)
    _parsePoller = null
  }
  parsing.value = false
  parseProgress.value = 0
}

async function onDeleteDoc() {
  const docId = moduleDetail.value?.primary_document?.id
  if (!docId) return
  await onDeleteDocById(docId)
}

async function onDownload() {
  try {
    const doc = moduleDetail.value?.primary_document
    if (!doc) return
    const res = await getXlsxQaDocumentDownloadUrl(moduleId.value, doc.id)
    window.open(res.url, '_blank')
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

async function onExportPdf() {
  if (pdfExportDisabled.value) return
  pdfExporting.value = true
  try {
    const resp = insightMode.value
      ? await exportXlsxQaInsightPdf(moduleId.value)
      : await exportXlsxQaConversationPdf(activeConvId.value, {
          message_ids: selectedMessageIds.value.length ? selectedMessageIds.value : undefined,
          include_subquestions: true,
          include_chart: true,
        })
    downloadBlobResponse(resp, insightMode.value ? '数据洞察报告.pdf' : '数据问答报告.pdf')
    ElMessage.success('PDF 已开始下载')
  } catch (e) {
    ElMessage.error(e.message || '导出 PDF 失败')
  } finally {
    pdfExporting.value = false
  }
}

function onExportPpt() {
  if (pptExportDisabled.value) return
  if (insightMode.value) {
    onExportInsightPpt()
    return
  }
  exportDialogVisible.value = true
}

async function onExportInsightPpt() {
  if (insightStreaming.value || isStreaming.value) return
  if (insightReportInfo.value?.status !== 'done') {
    ElMessage.warning('请先生成完整的数据洞察报告')
    return
  }
  insightExportDialogVisible.value = true
}

function insightPptExportFn(moduleId, _payload) {
  return exportXlsxQaInsightPptAsync(moduleId)
}

function downloadBlobResponse(resp, fallbackName) {
  const blob = resp?.data instanceof Blob ? resp.data : resp
  if (!(blob instanceof Blob)) return
  const cd = resp?.headers?.['content-disposition'] || resp?.headers?.['Content-Disposition'] || ''
  const m = cd.match(/filename\*=UTF-8''([^;]+)/i)
  const filename = m ? decodeURIComponent(m[1]) : fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function loadPreview() {
  const doc = moduleDetail.value?.primary_document
  if (!doc) return
  previewLoading.value = true
  try {
    preview.value = await previewXlsxQaDocument(moduleId.value, doc.id, 20)
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    previewLoading.value = false
  }
}

watch(rightTab, (v) => {
  if (v === 'preview' && !preview.value) loadPreview()
})

// ------------------- 多 Sheet 操作 -------------------

function toggleDocExpand(docId) {
  const s = new Set(expandedDocIds.value)
  if (s.has(docId)) s.delete(docId)
  else s.add(docId)
  expandedDocIds.value = s
}

function toggleSheetExpand(sheetId) {
  const s = new Set(expandedSheetIds.value)
  if (s.has(sheetId)) s.delete(sheetId)
  else s.add(sheetId)
  expandedSheetIds.value = s
}

function getSheetDetailTab(sheetId) {
  return sheetDetailTab.value[sheetId] || 'columns'
}

function setSheetDetailTab(sheetId, tab) {
  sheetDetailTab.value = { ...sheetDetailTab.value, [sheetId]: tab }
  if (tab === 'preview' && !sheetPreview.value[sheetId]) {
    loadSheetPreview(sheetId)
  }
}

async function loadSheetPreview(sheetId) {
  // Find the sheet to get docId
  let docId = null
  for (const doc of allDocuments.value) {
    if ((doc.sheets || []).some(s => s.id === sheetId)) {
      docId = doc.id
      break
    }
  }
  if (!docId) return
  sheetPreviewLoading.value = { ...sheetPreviewLoading.value, [sheetId]: true }
  try {
    const data = await previewXlsxQaSheet(moduleId.value, docId, sheetId, 20)
    sheetPreview.value = { ...sheetPreview.value, [sheetId]: data }
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    sheetPreviewLoading.value = { ...sheetPreviewLoading.value, [sheetId]: false }
  }
}

function getSheetPreviewRows(sheetId) {
  const p = sheetPreview.value[sheetId]
  if (!p?.columns?.length) return []
  const cols = p.columns
  return (p.rows || []).map((r) => {
    const o = {}
    cols.forEach((c, i) => {
      const v = r[i]
      o[c] = v === null || v === undefined ? '' : v
    })
    return o
  })
}

function startEditSheet(sh) {
  editingSheetId.value = sh.id
  editingSheetMd.value = sh.understanding_md || ''
}

function cancelEditSheet() {
  editingSheetId.value = null
  editingSheetMd.value = ''
}

async function saveEditSheet(sh) {
  const docId = sh._doc?.id || sh.document_id
  if (!docId) return
  try {
    const res = await updateSheetUnderstanding(moduleId.value, docId, sh.id, editingSheetMd.value)
    // Update local sheet data
    const doc = allDocuments.value.find(d => d.id === docId)
    const sheet = doc?.sheets?.find(s => s.id === sh.id)
    if (sheet) {
      sheet.understanding_md = res.understanding_md
    }
    ElMessage.success(t('wb.right.und.success'))
    editingSheetId.value = null
    editingSheetMd.value = ''
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('common.failed'))
  }
}

async function regenerateSheet(sh) {
  const docId = sh._doc?.id || sh.document_id
  if (!docId) return
  sheetRegenLoading.value = sh.id
  try {
    const res = await regenerateSheetUnderstanding(moduleId.value, docId, sh.id)
    // 更新本地 sheet 数据
    const doc = allDocuments.value.find(d => d.id === docId)
    const sheet = doc?.sheets?.find(s => s.id === sh.id)
    if (sheet) {
      sheet.understanding_md = res.understanding_md
      sheet.suggested_questions = res.suggested_questions
    }
    ElMessage.success(t('wb.right.und.success'))
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('common.failed'))
  } finally {
    sheetRegenLoading.value = null
  }
}

async function regenerateModuleSummaryDoc() {
  moduleSummaryLoading.value = true
  try {
    const res = await regenerateModuleSummary(moduleId.value)
    if (moduleDetail.value) moduleDetail.value.module_understanding_md = res.module_understanding_md
    ElMessage.success(t('wb.right.und.success'))
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || t('common.failed'))
  } finally {
    moduleSummaryLoading.value = false
  }
}

async function onDeleteDocById(docId) {
  try {
    await ElMessageBox.confirm(
      t('wb.deleteDoc.confirm'),
      t('wb.deleteDoc.title'),
      { type: 'warning' }
    )
  } catch { return }
  try {
    await deleteXlsxQaDocument(moduleId.value, docId)
    ElMessage.success(t('home.toast.deleted'))
    // 清空对话历史
    conversations.value = []
    activeConvId.value = null
    messages.value = []
    await loadModule()
    preview.value = null
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

function isSheetActive(sheetId) {
  if (activeSheetIds.value === null) return true  // 全选
  return activeSheetIds.value.includes(sheetId)
}

async function toggleActiveSheet(sheetId) {
  // 首次从"全选"变成"部分选"：初始化列表为全部
  if (activeSheetIds.value === null) {
    activeSheetIds.value = allSheets.value.map(s => s.id)
  }
  const idx = activeSheetIds.value.indexOf(sheetId)
  if (idx >= 0) {
    activeSheetIds.value = activeSheetIds.value.filter(id => id !== sheetId)
  } else {
    activeSheetIds.value = [...activeSheetIds.value, sheetId]
  }
  // 不能全不选
  if (!activeSheetIds.value.length) {
    activeSheetIds.value = [sheetId]
  }
  // 持久化到会话
  if (activeConvId.value) {
    try {
      await updateConversationSheets(activeConvId.value, activeSheetIds.value)
    } catch { /* ignore */ }
  }
}

async function resetActiveSheets() {
  activeSheetIds.value = null
  if (activeConvId.value) {
    try {
      await updateConversationSheets(activeConvId.value, allSheets.value.map(s => s.id))
    } catch { /* ignore */ }
  }
}

function toggleSheetSelect(idx) {
  const arr = selectedSheetIndices.value
  const pos = arr.indexOf(idx)
  if (pos >= 0) {
    selectedSheetIndices.value = arr.filter(i => i !== idx)
  } else {
    if (arr.length >= 5) {
      ElMessage.warning('最多选择 5 个工作表')
      return
    }
    selectedSheetIndices.value = [...arr, idx]
  }
}

async function confirmUploadWithSheets() {
  if (!pendingUploadFile.value || !selectedSheetIndices.value.length) return
  sheetSelectVisible.value = false
  const file = pendingUploadFile.value
  const indices = [...selectedSheetIndices.value]
  uploading.value = true
  uploadProgress.value = 0
  try {
    await uploadXlsxQaDocument(moduleId.value, file, {
      onProgress: (p) => (uploadProgress.value = p),
      sheetIndices: indices.length < pendingSheetNames.value.length ? indices : null,
    })
    ElMessage.success(t('wb.uploadOk'))
    await loadModule()
    _startParsePoller()
  } catch (err) {
    ElMessage.error(err.message || t('common.failed'))
  } finally {
    uploading.value = false
    uploadProgress.value = 0
    pendingUploadFile.value = null
    pendingSheetNames.value = []
    selectedSheetIndices.value = []
  }
}

// ------------------- 发送问题 -------------------

function askQuick(q) {
  questionInput.value = q
  onSubmit()
}

// 标记：本次 activeConvId 变更由程序内部触发，跳过 watch 自动 loadMessages
// 避免新建会话时异步 loadMessages 返回空数组，把刚乐观插入的 user/assistant 覆盖掉
const skipNextAutoLoad = ref(false)

async function ensureConversation() {
  if (activeConvId.value) return activeConvId.value
  const conv = await createXlsxQaConversation(moduleId.value)
  conversations.value.unshift({ ...conv })
  skipNextAutoLoad.value = true
  activeConvId.value = conv.id
  return conv.id
}

async function onSubmit() {
  const q = questionInput.value.trim()
  if (!q || isStreaming.value || !canAsk.value) return
  try {
    const convId = await ensureConversation()
    questionInput.value = ''

    // 清除上一轮的 think 状态
    moduleThinkContent.value = ''
    moduleThinkRelevantIds.value = []
    thinkCollapsed.value = false

    // 乐观插入 user 消息
    const userMsg = {
      id: `tmp-user-${Date.now()}`,
      _localKey: `tmp-user-${Date.now()}`,
      conversation_id: convId,
      role: 'user',
      content: q,
      status: 'ok',
      extras: null
    }
    const assistantMsg = {
      id: `tmp-ast-${Date.now()}`,
      _localKey: `tmp-ast-${Date.now()}`,
      _streaming: true,
      _stage: null,
      _think: null,
      conversation_id: convId,
      role: 'assistant',
      content: '',
      status: 'ok',
      extras: {
        plan_summary: '',
        subquestions: [],
        summary_markdown: '',
        follow_up_questions: []
      }
    }
    messages.value.push(userMsg, assistantMsg)
    // 关键：push 之后通过数组索引取回 reactive proxy，否则后续 onEvent 里用闭包
    // 变量写字段（extras.charts = ...、msg.id = ...）是写到原始对象，Vue 不会重渲染，
    // 会出现"图表 / PPT 按钮要退出重进才能看到"的症状。
    const reactiveAssistant = messages.value[messages.value.length - 1]
    scrollBottom()

    isStreaming.value = true
    abortCtrl.value = new AbortController()

    await askXlsxQaStream(
      convId,
      { question: q },
      {
        signal: abortCtrl.value.signal,
        onEvent: (evt, data) => handleSseEvent(reactiveAssistant, evt, data)
      }
    )

    reactiveAssistant._streaming = false
    // 异步刷新会话列表的 title / updated_at
    loadConversations()
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant') {
      last.status = 'failed'
      last.content = e.message || t('bubble.failNote')
      last._streaming = false
      last._stage = null
    }
  } finally {
    isStreaming.value = false
    abortCtrl.value = null
  }
}

function handleSseEvent(msg, evt, data) {
  if (!data) return
  const extras = msg.extras
  if (evt === 'module_plan') {
    // Stage 0: Module Planning think
    moduleThinkContent.value = data.think_content || ''
    moduleThinkRelevantIds.value = data.relevant_sheet_ids || []
    msg._think = {
      content: data.think_content || '',
      relevant_sheet_ids: data.relevant_sheet_ids || [],
    }
  } else if (evt === 'plan') {
    extras.plan_summary = data.plan_summary || ''
    extras.subquestions = (data.subquestions || []).map((sq) => ({
      id: sq.id,
      question: sq.question,
      purpose: sq.purpose || '',
      sql: '',
      sql_status: 'pending',
      columns: [],
      rows: [],
      total_rows: 0,
      error: null,
      target_sheet_id: sq.target_sheet_id || null,
      target_sheet_display_name: sq.target_sheet_display_name || null,
    }))
  } else if (evt === 'sql') {
    const sq = extras.subquestions.find((s) => s.id === data.subquestion_id)
    if (sq) {
      sq.sql = data.sql || ''
      sq.sql_status = data.error ? 'error' : 'running'
      if (data.error) sq.error = data.error
    }
  } else if (evt === 'sql_result') {
    const sq = extras.subquestions.find((s) => s.id === data.subquestion_id)
    if (sq) {
      sq.sql_status = data.sql_status || 'ok'
      sq.columns = data.columns || []
      sq.rows = data.rows || []
      sq.total_rows = data.total_rows || 0
      sq.truncated = data.truncated || false
      sq.error = data.error || null
    }
  } else if (evt === 'chart') {
    if (Array.isArray(data.charts) && data.charts.length) {
      extras.charts = data.charts
      extras.primary_chart_id = data.primary_id || data.charts[0].subquestion_id
      extras.chart = data.chart || data.charts.find((c) => c.subquestion_id === extras.primary_chart_id) || data.charts[0]
    } else if (data.chart) {
      extras.chart = data.chart
      extras.charts = [data.chart]
      extras.primary_chart_id = data.chart.subquestion_id
    }
  } else if (evt === 'summary') {
    extras.summary_markdown = data.summary_markdown || ''
    extras.follow_up_questions = data.follow_up_questions || []
  } else if (evt === 'done') {
    msg._streaming = false
    if (data?.state) {
      Object.assign(extras, data.state)
    }
  } else if (evt === 'error') {
    msg.status = 'failed'
    msg.content = data.message || t('bubble.failNote')
  } else if (evt === 'stage_start') {
    msg._stage = { stage: data.stage || '', message: data.message || '' }
  } else if (evt === 'stage_error') {
    // 后端会尽量把 message 以"用户问题语言"返回；前端只做兜底括号包装
    msg._stage = {
      stage: data.stage || '',
      message: data.message
        ? (lang.value === 'en' ? `(${data.message}, continuing…)` : `（${data.message}，继续下一步…）`)
        : (lang.value === 'en' ? '(Stage skipped, continuing…)' : '（该阶段跳过，继续下一步…）')
    }
  } else if (evt === 'user_message_saved') {
    // 服务端已落库，可拿 data.message_id 替换 _localKey（暂未用）
  } else if (evt === 'assistant_message_saved') {
    // 用真实的数据库 id 替换临时 id，这样 PPT 选中 / 导出按钮才能生效
    if (typeof data.message_id === 'number') {
      msg.id = data.message_id
      if (data.status) msg.status = data.status
    }
  } else if (evt === 'knowledge_card') {
    // 收到知识卡片事件，展示给用户
    if (data?.has_knowledge && Array.isArray(data.items) && data.items.length) {
      knowledgeCard.value.items = data.items.map((item) => ({
        alias: item.alias || '',
        maps_to: item.maps_to || '',
        column_hint: item.column_hint || null,
        description: item.description || '',
        sheet_id: item.sheet_id || null,
      }))
      knowledgeCard.value.visible = true
    }
  }
  scrollBottom()
}

function scrollBottom() {
  nextTick(() => {
    const el = scrollerRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
  })
}

// ------------------- 生命周期 -------------------

onMounted(async () => {
  loadShowSqlPref()
  loadHideRightPanelPref()
  loading.value = true
  try {
    await loadModule()
    await loadConversations()
    await loadInsightReportInfo()
    if (activeConvId.value) await loadMessages(activeConvId.value)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  if (abortCtrl.value) abortCtrl.value.abort()
  _stopParsePoller()
})

watch(activeConvId, (v) => {
  selectedMessageIds.value = []
  // 恢复会话的 Sheet 范围
  const conv = conversations.value.find(c => c.id === v)
  if (conv?.active_sheet_ids?.length) {
    activeSheetIds.value = conv.active_sheet_ids
  } else {
    activeSheetIds.value = null
  }
  if (skipNextAutoLoad.value) {
    skipNextAutoLoad.value = false
    return
  }
  if (v) loadMessages(v)
})
</script>

<style scoped>
.xq-workbench {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  background: #f8fafc;
}
.xq-wb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  padding: 14px 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.head-crumbs {
  font-size: 13px;
  color: #94a3b8;
}
.crumb-link {
  color: #64748b;
  text-decoration: none;
}
.crumb-link:hover {
  color: #2563eb;
}
.crumb-sep { margin: 0 6px; }
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lang-toggle {
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #475569;
}
.lang-toggle-text { font-size: 12px; }

.xq-wb-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 240px 1fr 340px;
}
.xq-wb-body.hide-right {
  grid-template-columns: 240px 1fr;
  gap: 12px;
  padding: 12px;
}

.xq-wb-side {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  border-bottom: 1px solid #f1f5f9;
}
.conv-list {
  flex: 1;
  overflow: auto;
  padding: 6px;
}
.conv-item {
  position: relative;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.12s ease;
}
.conv-item:hover {
  background: #f1f5f9;
}
.conv-item:hover .conv-del {
  opacity: 1;
}
.conv-item.is-active {
  background: #eff6ff;
  box-shadow: inset 2px 0 0 #2563eb;
}
.conv-title {
  font-size: 13px;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-insight-mark {
  position: absolute;
  right: 8px;
  bottom: 7px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  line-height: 16px;
  color: #0f766e;
  background: #ccfbf1;
  border: 1px solid #99f6e4;
}
.conv-insight-mark-dot {
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: #0f766e;
}
.conv-item--insight {
  background: #f0fdfa;
  padding-bottom: 26px;
}
.conv-item--insight.is-active {
  background: #ccfbf1;
  box-shadow: inset 2px 0 0 #0f766e;
}
.conv-meta {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}
.conv-del {
  position: absolute;
  top: 10px;
  right: 8px;
  opacity: 0;
  color: #ef4444;
  transition: opacity 0.12s ease;
}
.conv-empty {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  padding: 20px 0;
}

.xq-wb-main {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.messages-scroller {
  flex: 1;
  overflow: auto;
  padding: 20px 24px;
}

.messages-scroller--insight {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  min-height: 0;
}
.insight-entry-card {
  display: block;
  width: 100%;
  max-width: 440px;
  margin: 0 auto 28px;
  padding: 18px 20px 16px;
  text-align: left;
  border: none;
  border-radius: 16px;
  cursor: pointer;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 55%, #fdf4ff 100%);
  box-shadow:
    0 0 0 1px rgba(99, 102, 241, 0.18),
    0 12px 28px rgba(79, 70, 229, 0.08);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease;
}
.insight-entry-card:hover {
  transform: translateY(-2px);
  box-shadow:
    0 0 0 1px rgba(99, 102, 241, 0.28),
    0 16px 34px rgba(79, 70, 229, 0.12);
}
.insight-entry-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #4338ca;
  background: rgba(255, 255, 255, 0.85);
  padding: 4px 10px;
  border-radius: 999px;
  margin-bottom: 10px;
}
.insight-entry-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
  line-height: 1.35;
}
.insight-entry-desc {
  font-size: 13px;
  color: #475569;
  line-height: 1.55;
  margin: 0 0 14px;
}
.insight-entry-cta {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  padding: 8px 18px;
  border-radius: 999px;
}
.welcome {
  text-align: center;
  padding: 48px 16px;
}
.welcome-title {
  font-size: 16px;
  color: #1f2937;
  margin-bottom: 6px;
  font-weight: 600;
}
.welcome-desc {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 16px;
}
.welcome-samples {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}
.composer {
  border-top: 1px solid #f1f5f9;
  padding: 10px 12px 12px;
  background: #fff;
}
.composer.is-disabled {
  opacity: 0.7;
}
.composer-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
.composer-tip {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: #94a3b8;
}

.no-file-hint {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

/* 解析进度页 */
.parse-progress-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 60px;
  gap: 0;
}
.parse-progress-icon svg {
  width: 72px;
  height: 72px;
  margin-bottom: 20px;
  filter: drop-shadow(0 4px 12px rgba(16, 185, 129, 0.15));
}
.parse-progress-title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 6px;
}
.parse-progress-desc {
  font-size: 12.5px;
  color: #6b7280;
  text-align: center;
  line-height: 1.6;
  margin-bottom: 24px;
  max-width: 320px;
}
.parse-progress-bar-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 340px;
}
.parse-progress-bar {
  flex: 1;
  height: 6px;
  background: #e5e7eb;
  border-radius: 999px;
  overflow: hidden;
}
.parse-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #34d399);
  border-radius: 999px;
  transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}
.parse-progress-fill.is-done {
  background: linear-gradient(90deg, #10b981, #6ee7b7);
  transition: width 0.3s ease;
}
.parse-progress-pct {
  font-size: 12px;
  font-weight: 600;
  color: #10b981;
  min-width: 36px;
  text-align: right;
}

.xq-wb-right {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.right-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  padding: 12px 14px;
  border-bottom: 1px solid #f1f5f9;
}
.right-desc {
  color: #64748b;
  font-size: 12.5px;
  padding: 10px 14px;
  line-height: 1.55;
}
.right-upload {
  display: flex;
  flex-direction: column;
  padding: 0 14px 14px;
  gap: 10px;
}
.upload-tip {
  font-size: 12px;
  color: #64748b;
  text-align: center;
}
.doc-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.doc-info {
  padding: 10px 14px 12px;
  border-bottom: 1px solid #f1f5f9;
}
.doc-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #111827;
  font-size: 13px;
  word-break: break-all;
}
.doc-meta {
  margin-top: 4px;
  font-size: 11.5px;
  color: #94a3b8;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.right-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 14px;
}
.right-tabs :deep(.el-tabs__content) {
  overflow: auto;
}
.column-list {
  display: flex;
  flex-direction: column;
}
.column-row {
  padding: 8px 0;
  border-bottom: 1px dashed #f1f5f9;
}
.column-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.column-raw {
  font-size: 13px;
  color: #111827;
  font-weight: 500;
  word-break: break-all;
  min-width: 0;
  flex: 1;
}
.column-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.column-sub code {
  background: #f3f4f6;
  color: #4b5563;
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
}
.column-samples {
  font-size: 11.5px;
  color: #94a3b8;
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.preview-meta {
  margin-top: 8px;
  font-size: 11.5px;
  color: #94a3b8;
}

.understanding-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 520px;
  overflow: auto;
}
.understanding-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 6px;
  border-bottom: 1px dashed #e2e8f0;
}
.understanding-hint {
  font-size: 11.5px;
  color: #94a3b8;
  flex: 1 1 100%;
}
.understanding-md {
  font-size: 12.5px;
  line-height: 1.65;
  color: #1f2937;
  padding: 4px 2px 12px;
}
.understanding-md :deep(h2) {
  font-size: 13.5px;
  margin: 14px 0 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid #e2e8f0;
  color: #0f172a;
}
.understanding-md :deep(h3) { font-size: 13px; margin: 10px 0 4px; color: #334155; }
.understanding-md :deep(ul),
.understanding-md :deep(ol) { padding-left: 1.35em; margin: 4px 0; }
.understanding-md :deep(ol) { list-style-type: decimal; }
.understanding-md :deep(li) { margin: 2px 0; }
.understanding-md :deep(li::marker) { color: #64748b; }
.understanding-md :deep(blockquote),
.understanding-md :deep(.md-blockquote) {
  margin: 6px 0;
  padding: 8px 10px 8px 12px;
  border-left: 3px solid #38bdf8;
  border-radius: 0 6px 6px 0;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
}
.understanding-md :deep(.md-table-wrap) {
  margin: 6px 0;
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.understanding-md :deep(code) {
  background: #f1f5f9; padding: 1px 5px; border-radius: 3px; font-size: 11.5px;
}
.understanding-md :deep(strong) { color: #0f172a; }
.understanding-md :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 6px 0;
  font-size: 11.5px;
}
.understanding-md :deep(th),
.understanding-md :deep(td) {
  border: 1px solid #e2e8f0;
  padding: 4px 8px;
  text-align: left;
  white-space: nowrap;
}
.understanding-md :deep(th) {
  background: #f1f5f9;
  font-weight: 600;
  color: #334155;
}
.understanding-md :deep(tr:hover td) {
  background: #f8fafc;
}

/* 知识卡片 */
.knowledge-card {
  position: fixed;
  bottom: 80px;
  right: 24px;
  width: 420px;
  max-width: calc(100vw - 48px);
  background: #fff;
  border: 1px solid #e0e7ff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(99, 102, 241, 0.15);
  padding: 16px;
  z-index: 100;
}
.knowledge-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
}
.knowledge-card-desc {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 12px;
  line-height: 1.5;
}
.knowledge-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 320px;
  overflow-y: auto;
}
.knowledge-item {
  background: #f8faff;
  border: 1px solid #e0e7ff;
  border-radius: 8px;
  padding: 10px 12px;
}
.ki-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.ki-field {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}
.ki-label {
  color: #6b7280;
  white-space: nowrap;
}
.ki-value {
  color: #374151;
  font-weight: 500;
}
.ki-field code {
  background: #eef2ff;
  color: #4f46e5;
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 3px;
}
.knowledge-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

/* 多文档面板 */
.multi-doc-panel {
  overflow-y: auto;
}
.right-title-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.doc-card {
  border-bottom: 1px solid #f1f5f9;
}
.doc-card:last-child {
  border-bottom: none;
}
.doc-card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  cursor: pointer;
  transition: background 0.12s ease;
}
.doc-card-head:hover {
  background: #f8fafc;
}
.doc-expand-icon {
  font-size: 12px;
  color: #94a3b8;
  flex-shrink: 0;
  transition: transform 0.15s ease;
}
.doc-card-info {
  flex: 1;
  min-width: 0;
}
.doc-card-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 500;
  color: #111827;
}
.doc-card-filename {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-card-meta {
  margin-top: 2px;
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  gap: 10px;
}
.doc-sheet-list {
  padding: 0 14px 8px 28px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sheet-item {
  display: flex;
  flex-direction: column;
}
.sheet-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  border-radius: 6px;
  background: #f8fafc;
  transition: background 0.1s ease;
  cursor: pointer;
}
.sheet-row:hover {
  background: #f1f5f9;
}
.sheet-row.is-expanded {
  background: #eff6ff;
  border-radius: 6px 6px 0 0;
}
.sheet-expand-icon {
  font-size: 11px;
  color: #94a3b8;
  flex-shrink: 0;
  margin-right: 4px;
}
.sheet-row-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.sheet-row-name {
  display: flex;
  align-items: center;
  gap: 6px;
}
.sheet-name-text {
  font-size: 12px;
  color: #374151;
  font-weight: 500;
}
.sheet-row-meta {
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  gap: 8px;
}
.sheet-empty {
  font-size: 11px;
  color: #94a3b8;
  text-align: center;
  padding: 8px 0;
}

/* Sheet 详情面板 */
.sheet-detail-panel {
  border: 1px solid #e0e7ff;
  border-top: none;
  border-radius: 0 0 6px 6px;
  background: #fff;
  padding: 8px 10px;
}
.sheet-detail-tabs {
  min-height: 0;
}
.sheet-detail-tabs :deep(.el-tabs__header) {
  margin-bottom: 6px;
}
.sheet-detail-tabs :deep(.el-tabs__content) {
  overflow: auto;
  max-height: 320px;
}
.column-list-compact {
  max-height: 240px;
  overflow-y: auto;
}
.understanding-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.understanding-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* 多文档 tabs */
.multi-doc-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.multi-doc-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  padding: 0 14px;
}
.multi-doc-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.multi-doc-tab-head {
  display: flex;
  justify-content: flex-end;
  padding: 0 14px 6px;
}

/* 文件理解 pane */
.file-understanding-pane {
  padding: 10px 14px 14px;
}
.file-understanding-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

/* Sheet 范围选择器 */
.sheet-scope {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e5e7eb;
  min-height: 36px;
}
.sheet-scope-label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-right: 2px;
}
.sheet-scope-chip {
  cursor: pointer;
  transition: all 0.12s ease;
  user-select: none;
}
.sheet-scope-chip:hover {
  opacity: 0.85;
}

/* Think Card */
.think-card {
  margin: 0 0 12px;
  padding: 10px 14px;
  background: #f5f3ff;
  border: 1px solid #e0e7ff;
  border-radius: 10px;
  transition: all 0.2s ease;
}
.think-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.think-card-title {
  font-size: 12.5px;
  font-weight: 600;
  color: #4f46e5;
}
.think-card-body {
  font-size: 12.5px;
  line-height: 1.6;
  color: #374151;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Sheet 选择对话框 */
.sheet-select-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 300px;
  overflow-y: auto;
}
.sheet-select-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.1s ease;
  border: 1px solid transparent;
}
.sheet-select-row:hover {
  background: #f8fafc;
}
.sheet-select-row.is-selected {
  background: #eef2ff;
  border-color: #c7d2fe;
}
.sheet-select-name {
  font-size: 13px;
  color: #111827;
  font-weight: 500;
}
.sheet-select-idx {
  font-size: 11px;
  color: #94a3b8;
}
.sheet-select-empty {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  padding: 20px;
}
.sheet-select-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #f1f5f9;
}
.sheet-select-hint {
  font-size: 12px;
  color: #64748b;
}
</style>
