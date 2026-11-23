<template>
  <div class="autobi-page">
    <PageHeader
      :breadcrumbs="[{ label: '实验中心' }]"
    />

    <div class="autobi-body">
      <aside class="folder-aside">
        <div class="folder-list">
          <div
            v-for="(f, folderIndex) in folders"
            :key="f.id"
            class="folder-row"
            :class="{ 'is-active': f.id === selectedFolderId }"
            @click="onSelectFolder(f.id)"
          >
            <div class="folder-row-main">
              <el-icon class="folder-item-icon"><Folder /></el-icon>
              <span class="folder-item-text">{{ f.name }}</span>
            </div>
            <el-dropdown trigger="click" @click.stop>
              <button type="button" class="folder-more-btn" aria-label="文件夹操作" @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="openRenameFolderDialog(f)">修改名称</el-dropdown-item>
                  <el-dropdown-item :disabled="folderIndex === 0" @click="handleFolderMove(f, 'up')">
                    上移
                  </el-dropdown-item>
                  <el-dropdown-item
                    :disabled="folderIndex === folders.length - 1"
                    @click="handleFolderMove(f, 'down')"
                  >
                    下移
                  </el-dropdown-item>
                  <el-dropdown-item divided :disabled="f.is_system" @click="handleFolderDelete(f)">
                    删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
        <div class="folder-footer">
          <el-button class="folder-create-btn" plain @click="openCreateFolderDialog">
            创建文件夹
          </el-button>
        </div>
      </aside>

      <div class="autobi-main">
        <!-- 工具栏：新增、导入与搜索 -->
        <div class="toolbar">
          <el-button type="primary" class="btn-add" :icon="Plus" @click="handleAdd">
            新增
          </el-button>
          <el-button :icon="Upload" :loading="labImportReading" :disabled="labImportLoading" @click="labImportFileRef?.click()">
            导入实验室
          </el-button>
          <input ref="labImportFileRef" type="file" accept=".json,application/json" hidden @change="onLabImportFile" />
          <div class="toolbar-spacer" />
          <el-input
            v-model="searchKeyword"
            class="search-input"
            placeholder="请输入关键字"
            clearable
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>

        <!-- 卡片网格 -->
        <div class="card-list">
          <div class="card-grid">
            <article
              v-for="item in filteredItems"
              :key="item.id"
              class="autobi-card"
            >
              <!-- 顶部：图片+名称+时间+删除 -->
              <div class="card-head">
                <div class="card-logo-wrap">
                  <img src="../assets/images/autobiCardLogo.png" alt="" class="card-logo-img" />
                </div>
                <div class="card-meta">
                  <h3 class="card-title" :title="item.name">{{ item.name }}</h3>
                  <p class="card-time">创建时间：{{ formatDate(item.created_at) }}</p>
                </div>
                <div class="card-head-actions">
                  <button type="button" class="card-icon-btn card-delete-btn" :aria-label="`删除实验室 ${item.name}`" @click="handleDelete(item)">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 4h12M5.333 4V2.667h5.334V4M6.667 7.333v4M9.333 7.333v4M3.333 4l.667 9.333h8L12.667 4H3.333z" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </button>
                </div>
              </div>

              <!-- 描述 -->
              <div class="card-desc-box">
                <p class="card-desc" :title="item.description || '暂无描述'">{{ item.description || '暂无描述' }}</p>
              </div>

              <!-- API ID -->
              <div class="card-api-box">
                <span class="card-api-label">API ID:</span>
                <code class="card-api-value">{{ item.api_access_id || '—' }}</code>
                <span class="card-api-hint">（对外调用主键）</span>
              </div>

              <!-- 底部操作 -->
              <div class="card-actions">
                <button type="button" class="action-btn action-lab" @click="openLaboratory(item)">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path fill-rule="evenodd" clip-rule="evenodd" d="M4.83353 2.99996H3.5002V1.66663H12.5002V2.99996H11.1669V5.7124L12.9556 10.4823L13.7585 12.5088C14.1053 13.384 13.4604 14.3333 12.519 14.3333H3.59953C2.68503 14.3333 2.04197 13.4336 2.33798 12.5684L3.12256 10.275L4.83353 5.7124V2.99996ZM6.16686 2.99996V5.95418L4.54703 10.2737C4.79293 10.4262 5.11462 10.5658 5.47882 10.6196C6.01719 10.6991 6.68513 10.5984 7.4029 9.99104C8.44638 9.10809 9.58947 8.96463 10.5656 9.14905C10.7429 9.18254 10.9149 9.22676 11.0804 9.27918L9.83353 5.95418V2.99996H6.16686ZM11.7765 11.1261C11.4439 10.8664 10.9153 10.572 10.3181 10.4592C9.67203 10.3371 8.95401 10.4252 8.26416 11.0089C7.24859 11.8682 6.19431 12.073 5.28407 11.9386C4.83844 11.8728 4.43641 11.7275 4.09561 11.5499L3.59953 13L12.519 13L11.7765 11.1261ZM8.0002 7.50329V7.49996H9.33353V7.50329H8.0002Z" fill="currentColor"/></svg>
                  实验室
                </button>
                <button type="button" class="action-btn action-default" @click="openSettings(item)">
                  <svg width="16" height="16" viewBox="0 0 18 18" fill="none"><path fill-rule="evenodd" clip-rule="evenodd" d="M6.32617 2.3239C6.46142 1.83698 6.90477 1.5 7.41013 1.5H10.5901C11.0954 1.5 11.5388 1.83698 11.674 2.3239L12.0575 3.70446L13.445 3.34627C13.9343 3.21994 14.4478 3.4354 14.7005 3.87305L16.2904 6.62696C16.5431 7.06461 16.4729 7.61704 16.1189 7.97764L15.1151 9L16.1189 10.0224C16.4729 10.383 16.5431 10.9354 16.2904 11.373L14.7005 14.127C14.4478 14.5646 13.9343 14.7801 13.445 14.6537L12.0575 14.2955L11.674 15.6761C11.5388 16.163 11.0954 16.5 10.5901 16.5H7.41013C6.90477 16.5 6.46142 16.163 6.32617 15.6761L5.9427 14.2956L4.55554 14.6537C4.06622 14.7801 3.55272 14.5646 3.30004 14.127L1.71007 11.373C1.45739 10.9354 1.52755 10.383 1.88161 10.0224L2.88544 9L1.88161 7.97764C1.52755 7.61704 1.45739 7.06461 1.71007 6.62695L3.30004 3.87305C3.55272 3.4354 4.06622 3.21994 4.55554 3.34626L5.9427 3.70439L6.32617 2.3239ZM7.69516 3L7.28943 4.46062C7.12528 5.05154 6.51808 5.40211 5.92425 5.24881L4.45656 4.86989L3.15163 7.13011L4.21372 8.21182C4.6434 8.64943 4.64341 9.35057 4.21372 9.78819L3.15163 10.8699L4.45656 13.1301L5.92425 12.7512C6.51808 12.5979 7.12529 12.9485 7.28943 13.5394L7.69516 15H10.305L10.7108 13.5393C10.8749 12.9484 11.4821 12.5978 12.076 12.7511L13.5439 13.1301L14.8489 10.8699L13.7868 9.78819C13.3571 9.35057 13.3571 8.64943 13.7868 8.21182L14.8489 7.13011L13.5439 4.8699L12.076 5.24888C11.4821 5.40219 10.8749 5.05162 10.7108 4.4607L10.305 3H7.69516ZM9.00009 7.5C8.17167 7.5 7.50009 8.17157 7.50009 9C7.50009 9.82843 8.17167 10.5 9.00009 10.5C9.82852 10.5 10.5001 9.82843 10.5001 9C10.5001 8.17157 9.82852 7.5 9.00009 7.5ZM6.00009 9C6.00009 7.34315 7.34324 6 9.00009 6C10.6569 6 12.0001 7.34315 12.0001 9C12.0001 10.6569 10.6569 12 9.00009 12C7.34324 12 6.00009 10.6569 6.00009 9Z" fill="currentColor"/></svg>
                  设置
                </button>
                <button type="button" class="action-btn action-default" @click="openApiDocs(item)">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path fill-rule="evenodd" clip-rule="evenodd" d="M6.32626 13.7952L8.41004 1.97754L9.72312 2.20907L7.63934 14.0268L6.32626 13.7952ZM2.74939 7.99997L6.04922 4.70014L5.10641 3.75733L0.86377 7.99997L5.10641 12.2426L6.04922 11.2998L2.74939 7.99997ZM10.8897 3.75733L15.1324 7.99997L10.8897 12.2426L9.94691 11.2998L13.2467 7.99997L9.94691 4.70014L10.8897 3.75733Z" fill="currentColor"/></svg>
                  API调用
                </button>
                <button type="button" class="action-btn action-default" @click="openCloneDialog(item)">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M5.5 2.5a1 1 0 0 0-1 1v1H3a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1v-1.5h1a1 1 0 0 0 1-1v-7a1 1 0 0 0-1-1h-7Zm6.5 2v5h-1V6a1 1 0 0 0-1-1H6V3.5h6ZM4.5 6.5h5V13h-5V6.5Z" fill="currentColor"/></svg>
                  克隆
                </button>
                <button type="button" class="action-btn action-default lab-export-btn" :disabled="labExportingIds.has(item.id)" @click="handleLabExport(item)">
                  <el-icon><Download /></el-icon>
                  {{ labExportingIds.has(item.id) ? '正在导出…' : '导出实验室' }}
                </button>
              </div>
            </article>
          </div>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="labImportVisible"
      title="导入实验室"
      width="480px"
      class="autobi-dialog"
      append-to-body
      :close-on-click-modal="!labImportLoading"
      :close-on-press-escape="!labImportLoading"
      :show-close="!labImportLoading"
      @closed="resetLabImport"
    >
      <el-alert title="将新建实验室并保留配置；模型和知识库需重新选择。" type="info" :closable="false" show-icon />
      <p class="lab-import-filename">文件：{{ labImportFileName }}</p>
      <el-form label-position="top" :disabled="labImportLoading">
        <el-form-item label="目标文件夹" required>
          <el-select v-model="labImportForm.folder_id" placeholder="请选择文件夹" style="width: 100%">
            <el-option v-for="f in folders" :key="f.id" :label="f.name" :value="f.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="实验室名称" required>
          <el-input v-model="labImportForm.name" maxlength="255" show-word-limit placeholder="请输入名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="labImportLoading" @click="labImportVisible = false">取消</el-button>
        <el-button type="primary" :loading="labImportLoading" @click="submitLabImport">确认导入</el-button>
      </template>
    </el-dialog>

    <!-- 新增：仅名称 + 描述 -->
    <el-dialog
      v-model="dialogVisible"
      title="新增"
      width="480px"
      class="autobi-dialog"
      append-to-body
      @close="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top">
        <el-form-item label="所属文件夹" prop="folder_id" required>
          <el-select v-model="form.folder_id" placeholder="请选择文件夹" style="width: 100%">
            <el-option v-for="f in folders" :key="f.id" :label="f.name" :value="f.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" prop="name" required>
          <el-input v-model="form.name" placeholder="请输入名称" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            placeholder="请输入描述"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" class="btn-primary-brand" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="renameFolderVisible"
      title="修改文件夹名称"
      width="400px"
      append-to-body
      @close="renameFolderId = null; renameFolderName = ''"
    >
      <el-form label-position="top">
        <el-form-item label="文件夹名称" required>
          <el-input
            v-model="renameFolderName"
            placeholder="请输入文件夹名称"
            maxlength="128"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameFolderVisible = false">取消</el-button>
        <el-button
          type="primary"
          class="btn-primary-brand"
          :loading="renameFolderLoading"
          @click="submitRenameFolder"
        >
          确定
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="createFolderVisible"
      title="创建文件夹"
      width="400px"
      append-to-body
      @close="newFolderName = ''"
    >
      <el-form label-position="top">
        <el-form-item label="文件夹名称" required>
          <el-input v-model="newFolderName" placeholder="请输入文件夹名称" maxlength="128" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createFolderVisible = false">取消</el-button>
        <el-button type="primary" class="btn-primary-brand" :loading="createFolderLoading" @click="submitCreateFolder">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 设置：多步骤配置（保存为 config_json，对齐 OpenTrek completions 结构） -->
    <el-dialog
      v-model="settingsVisible"
      :title="settingsTitle"
      width="min(1080px, 96vw)"
      top="3vh"
      class="autobi-settings-dialog"
      append-to-body
    >
      <!-- 步骤条 -->
      <div class="settings-steps-bar">
        <div
          v-for="(step, idx) in settingsSteps"
          :key="step.id"
          class="step-item"
          :class="{ 'is-active': currentStepIndex === idx, 'is-done': step.completed && !step.disabled, 'is-disabled': step.disabled }"
          @click="goToStep(idx)"
        >
          <div class="step-dot">
            <el-icon v-if="step.completed"><Check /></el-icon>
            <span v-else>{{ idx + 1 }}</span>
          </div>
          <span class="step-title">{{ step.label }}</span>
        </div>
      </div>

      <!-- 模块描述 -->
      <div class="settings-module-desc">
        <el-icon><component :is="currentStepIcon" /></el-icon>
        <span>{{ currentStepDesc }}</span>
      </div>

      <!-- 内容区固定高度，可滚动 -->
      <div class="settings-content-wrap">
        <div class="settings-body">
          <!-- 00 数据准备 -->
          <section v-show="currentStepIndex === 0" class="settings-block">
            <div class="module-switch-row">
              <span class="module-switch-label">
                <el-icon><Collection /></el-icon>
                数据准备
              </span>
            </div>
            <div class="module-content">
              <el-form label-position="left" class="compact-form" label-width="140px">
                <el-form-item label="文件夹">
                  <el-select v-model="settingsFolderId" placeholder="请选择" style="width: 100%">
                    <el-option v-for="f in folders" :key="f.id" :label="f.name" :value="f.id" />
                  </el-select>
                </el-form-item>
                <el-form-item label="知识库">
                  <el-select
                    v-model="settings.knowledgeBaseId"
                    filterable
                    clearable
                    placeholder="请选择知识库"
                    style="width: 100%"
                    :loading="knowledgeBasesLoading"
                  >
                    <el-option
                      v-for="kb in knowledgeBaseList"
                      :key="kb.id"
                      :label="`${kb.name} (ID: ${kb.id})`"
                      :value="kb.id"
                    />
                  </el-select>
                </el-form-item>
              </el-form>
            </div>
          </section>

          <!-- 01 改写配置 -->
          <section v-show="currentStepIndex === 1" class="settings-block">
            <div class="module-switch-row" @click="toggleRewriteExpanded">
              <span class="module-switch-label">
                <el-icon class="module-arrow" :class="{ 'is-expanded': rewriteExpanded }"><ArrowRight /></el-icon>
                知识改写
              </span>
              <el-switch v-model="settings.rewriteEnabled" @click.stop @change="val => { if(val) rewriteExpanded = true; }" />
            </div>
            <el-collapse-transition>
              <div v-show="rewriteExpanded || settings.rewriteEnabled" class="module-content">
                <el-form label-position="left" class="compact-form" label-width="140px">
                  <el-form-item label="关键词召回">
                    <el-switch v-model="settings.keywordRecallEnabled" />
                  </el-form-item>
                  <el-form-item v-if="settings.keywordRecallEnabled" label="召回数量">
                    <el-input-number v-model="settings.rewriteKeywordMaxRecall" :min="1" :max="200" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="模型">
                    <AutobiProviderModelSelect
                      :providers="usableProviders"
                      :provider-id="settings.rewriteProviderId"
                      :model-name="settings.rewriteModelName"
                      @update:provider-id="settings.rewriteProviderId = $event"
                      @update:model-name="settings.rewriteModelName = $event"
                    />
                  </el-form-item>
                  <el-form-item label="采样概率">
                    <el-input-number v-model="settings.rewriteTopP" :min="0" :max="1" :step="0.1" :precision="1" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="采样数量">
                    <el-input-number v-model="settings.rewriteTopK" :min="1" :max="200" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="温度">
                    <el-input-number v-model="settings.rewriteTemperature" :min="0" :max="2" :step="0.1" :precision="1" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="最大输出">
                    <el-input-number v-model="settings.rewriteMaxOut" :min="256" :max="32768" :step="256" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="最大上下文">
                    <el-input-number v-model="settings.rewriteMaxCtx" :min="1024" :max="32768" :step="256" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="Prompt">
                    <el-input v-model="settings.rewritePrompt" type="textarea" :rows="2" placeholder="系统提示词..." />
                  </el-form-item>
                  <el-form-item><el-checkbox v-model="settings.rewriteDisclaimer">同意使用第三方模型条款</el-checkbox></el-form-item>
                </el-form>
              </div>
            </el-collapse-transition>
          </section>

          <!-- 02 召回配置 -->
          <section v-show="currentStepIndex === 2" class="settings-block">
            <!-- 表/列召回子模块 -->
            <div class="sub-module">
              <div class="sub-module-header" @click="toggleRecallColExpanded">
                <span class="sub-module-title">
                  <el-icon class="sub-module-arrow" :class="{ 'is-expanded': recallColExpanded }"><ArrowRight /></el-icon>
                  表/列召回
                </span>
              </div>
              <el-collapse-transition>
                <div v-show="recallColExpanded" class="sub-module-content">
                  <el-form label-position="left" class="compact-form" label-width="140px">
                    <el-form-item label="召回数量">
                      <el-input-number v-model="settings.recallColMax" :min="1" :max="100" style="width: 100%" />
                    </el-form-item>
                    <el-form-item label="阈值">
                      <el-slider v-model="settings.recallColThreshold" :min="0" :max="1" :step="0.05" />
                    </el-form-item>
                  </el-form>
                </div>
              </el-collapse-transition>
            </div>

            <!-- 值召回子模块 -->
            <div class="sub-module">
              <div class="sub-module-header" @click="toggleRecallValExpanded">
                <span class="sub-module-title">
                  <el-icon class="sub-module-arrow" :class="{ 'is-expanded': recallValExpanded }"><ArrowRight /></el-icon>
                  值召回
                </span>
              </div>
              <el-collapse-transition>
                <div v-show="recallValExpanded" class="sub-module-content">
                  <el-form label-position="left" class="compact-form" label-width="140px">
                    <el-form-item label="召回数量">
                      <el-input-number v-model="settings.recallValMax" :min="1" :max="100" style="width: 100%" />
                    </el-form-item>
                    <el-form-item label="阈值">
                      <el-slider v-model="settings.recallValThreshold" :min="0" :max="1" :step="0.05" />
                    </el-form-item>
                    <el-form-item label="多列同值">
                      <el-switch v-model="settings.recallValMultiColEnabled" />
                    </el-form-item>
                    <template v-if="settings.recallValMultiColEnabled">
                      <el-form-item label="多列每路数量">
                        <el-input-number v-model="settings.recallValMultiColMax" :min="1" :max="100" style="width: 100%" />
                      </el-form-item>
                      <el-form-item label="多列阈值">
                        <el-slider v-model="settings.recallValMultiColThreshold" :min="0" :max="1" :step="0.05" />
                      </el-form-item>
                    </template>
                  </el-form>
                </div>
              </el-collapse-transition>
            </div>

            <!-- SQL样例召回子模块 -->
            <div class="sub-module">
              <div class="sub-module-header" @click="toggleRecallSqlExpanded">
                <span class="sub-module-title">
                  <el-icon class="sub-module-arrow" :class="{ 'is-expanded': recallSqlExpanded }"><ArrowRight /></el-icon>
                  SQL样例召回
                </span>
              </div>
              <el-collapse-transition>
                <div v-show="recallSqlExpanded" class="sub-module-content">
                  <el-form label-position="left" class="compact-form" label-width="140px">
                    <el-form-item label="召回数量">
                      <el-input-number v-model="settings.recallSqlMax" :min="1" :max="20" style="width: 100%" />
                    </el-form-item>
                    <el-form-item label="阈值">
                      <el-slider v-model="settings.recallSqlThreshold" :min="0" :max="1" :step="0.05" />
                    </el-form-item>
                  </el-form>
                </div>
              </el-collapse-transition>
            </div>

            <!-- NER召回子模块 -->
            <div class="sub-module">
              <div class="sub-module-header" @click="toggleNerExpanded">
                <span class="sub-module-title">
                  <el-icon class="sub-module-arrow" :class="{ 'is-expanded': nerExpanded }"><ArrowRight /></el-icon>
                  NER召回
                </span>
                <el-switch v-model="settings.nerRetrievalEnabled" @click.stop />
              </div>
              <el-collapse-transition>
                <div v-show="nerExpanded || settings.nerRetrievalEnabled" class="sub-module-content">
                  <el-form label-position="left" class="compact-form" label-width="140px">
                    <el-form-item label="模型">
                      <AutobiProviderModelSelect
                        :providers="usableProviders"
                        :provider-id="settings.nerRetrievalProviderId"
                        :model-name="settings.nerRetrievalModelName"
                        @update:provider-id="settings.nerRetrievalProviderId = $event"
                        @update:model-name="settings.nerRetrievalModelName = $event"
                      />
                    </el-form-item>
                    <el-form-item label="采样概率">
                      <el-input-number v-model="settings.nerTopP" :min="0" :max="1" :step="0.1" :precision="1" style="width: 100%" />
                    </el-form-item>
                    <el-form-item label="采样数量">
                      <el-input-number v-model="settings.nerTopK" :min="1" :max="200" style="width: 100%" />
                    </el-form-item>
                    <el-form-item label="温度">
                      <el-input-number v-model="settings.nerTemperature" :min="0" :max="2" :step="0.1" :precision="1" style="width: 100%" />
                    </el-form-item>
                    <el-form-item label="最大输出">
                      <el-input-number v-model="settings.nerMaxOut" :min="256" :max="32768" :step="256" style="width: 100%" />
                    </el-form-item>
                    <el-form-item label="最大上下文">
                      <el-input-number v-model="settings.nerMaxCtx" :min="1024" :max="32768" :step="256" style="width: 100%" />
                    </el-form-item>
                    <el-form-item><el-checkbox v-model="settings.nerRetrievalDisclaimer">同意使用第三方模型条款</el-checkbox></el-form-item>
                  </el-form>
                </div>
              </el-collapse-transition>
            </div>
          </section>

          <!-- 03 生成SQL -->
          <section v-show="currentStepIndex === 3" class="settings-block">
            <div class="module-switch-row">
              <span class="module-switch-label">
                <el-icon><DataAnalysis /></el-icon>
                生成SQL
              </span>
            </div>
            <div class="module-content">
              <el-form label-position="left" class="compact-form" label-width="140px">
                <el-form-item label="模型">
                  <AutobiProviderModelSelect
                    :providers="usableProviders"
                    :provider-id="settings.sqlProviderId"
                    :model-name="settings.sqlModelName"
                    @update:provider-id="settings.sqlProviderId = $event"
                    @update:model-name="settings.sqlModelName = $event"
                  />
                </el-form-item>
                <el-form-item label="采样概率">
                  <el-input-number v-model="settings.sqlTopP" :min="0" :max="1" :step="0.1" :precision="1" style="width: 100%" />
                </el-form-item>
                <el-form-item label="采样数量">
                  <el-input-number v-model="settings.sqlTopK" :min="1" :max="200" style="width: 100%" />
                </el-form-item>
                <el-form-item label="温度">
                  <el-input-number v-model="settings.sqlTemperature" :min="0" :max="2" :step="0.1" :precision="1" style="width: 100%" />
                </el-form-item>
                <el-form-item label="最大输出">
                  <el-input-number v-model="settings.sqlMaxOut" :min="256" :max="32768" :step="256" style="width: 100%" />
                </el-form-item>
                <el-form-item label="最大上下文">
                  <el-input-number v-model="settings.sqlMaxCtx" :min="1024" :max="32768" :step="256" style="width: 100%" />
                </el-form-item>
                <el-form-item label="Prompt">
                  <el-input v-model="settings.sqlPrompt" type="textarea" :rows="2" placeholder="系统提示词..." />
                </el-form-item>
                <el-form-item><el-checkbox v-model="settings.sqlDisclaimer">同意使用第三方模型条款</el-checkbox></el-form-item>
              </el-form>
            </div>
          </section>

          <!-- 04 SQL改写 -->
          <section v-show="currentStepIndex === 4" class="settings-block">
            <div class="module-switch-row" @click="toggleSqlPermissionRewriteExpanded">
              <span class="module-switch-label">
                <el-icon class="module-arrow" :class="{ 'is-expanded': sqlPermissionRewriteExpanded }"><ArrowRight /></el-icon>
                SQL改写
              </span>
              <el-switch v-model="settings.sqlPermissionRewriteEnabled" @click.stop @change="val => { if(val) sqlPermissionRewriteExpanded = true; }" />
            </div>
            <el-collapse-transition>
              <div v-show="sqlPermissionRewriteExpanded || settings.sqlPermissionRewriteEnabled" class="module-content">
                <el-form label-position="left" class="compact-form" label-width="140px">
                  <el-form-item label="工作流">
                    <div class="sql-agent-picker">
                      <div v-if="selectedSqlPermissionAgent" class="sql-agent-card">
                        <div class="sql-agent-card__icon">{{ selectedSqlPermissionAgent.icon || '*' }}</div>
                        <div class="sql-agent-card__main">
                          <div class="sql-agent-card__title">{{ selectedSqlPermissionAgent.name }}</div>
                          <div class="sql-agent-card__desc">{{ selectedSqlPermissionAgent.description || '—' }}</div>
                          <div class="sql-agent-card__meta">
                            ID: {{ selectedSqlPermissionAgent.id }}
                            <span v-if="selectedSqlPermissionVersion"> · {{ selectedSqlPermissionVersion.name || `版本 #${ selectedSqlPermissionVersion.id }` }}</span>
                          </div>
                        </div>
                        <el-button text type="danger" size="small" @click="clearSqlPermissionAgent">清空</el-button>
                      </div>
                      <el-select
                        v-model="settings.sqlPermissionRewriteAgentId"
                        filterable
                        clearable
                        :loading="agentAppsLoading"
                        placeholder="选择工作流 ID"
                        style="width: 100%; margin-top: 10px"
                        @change="onSqlPermissionAgentChange"
                      >
                        <el-option
                          v-for="app in agentApps"
                          :key="app.id"
                          :label="`${app.name} (ID: ${app.id})`"
                          :value="app.id"
                        />
                      </el-select>
                    </div>
                  </el-form-item>
                  <el-form-item label="版本">
                    <el-select
                      v-model="settings.sqlPermissionRewriteVersionId"
                      filterable
                      clearable
                      :disabled="!settings.sqlPermissionRewriteAgentId"
                      placeholder="选择工作流版本"
                      style="width: 100%"
                    >
                      <el-option
                        v-for="v in sqlPermissionVersionOptions"
                        :key="v.id"
                        :label="formatSqlPermissionVersionLabel(v)"
                        :value="v.id"
                      />
                    </el-select>
                  </el-form-item>
                  <p class="sql-permission-hint">
                    调用该工作流用于sql改写，input默认为生成的sql，features为调用实验室的参数。需要工作流返回的内容为sql。
                  </p>
                </el-form>
              </div>
            </el-collapse-transition>
          </section>

          <!-- 05 总结摘要 -->
          <section v-show="currentStepIndex === 5" class="settings-block">
            <div class="module-switch-row" @click="toggleSummaryExpanded">
              <span class="module-switch-label">
                <el-icon class="module-arrow" :class="{ 'is-expanded': summaryExpanded }"><ArrowRight /></el-icon>
                总结摘要
              </span>
              <el-switch v-model="settings.summaryEnabled" @click.stop @change="val => { if(val) summaryExpanded = true; }" />
            </div>
            <el-collapse-transition>
              <div v-show="summaryExpanded || settings.summaryEnabled" class="module-content">
                <el-form label-position="left" class="compact-form" label-width="140px">
                  <el-form-item label="模型">
                    <AutobiProviderModelSelect
                      :providers="usableProviders"
                      :provider-id="settings.summaryProviderId"
                      :model-name="settings.summaryModelName"
                      @update:provider-id="settings.summaryProviderId = $event"
                      @update:model-name="settings.summaryModelName = $event"
                    />
                  </el-form-item>
                  <el-form-item label="采样概率">
                    <el-input-number v-model="settings.summaryTopP" :min="0" :max="1" :step="0.1" :precision="1" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="采样数量">
                    <el-input-number v-model="settings.summaryTopK" :min="1" :max="200" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="温度">
                    <el-input-number v-model="settings.summaryTemperature" :min="0" :max="2" :step="0.1" :precision="1" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="最大输出">
                    <el-input-number v-model="settings.summaryMaxOut" :min="256" :max="32768" :step="256" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="最大上下文">
                    <el-input-number v-model="settings.summaryMaxCtx" :min="1024" :max="32768" :step="256" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="Prompt">
                    <el-input v-model="settings.summaryPrompt" type="textarea" :rows="2" placeholder="系统提示词..." />
                  </el-form-item>
                  <el-form-item><el-checkbox v-model="settings.summaryDisclaimer">同意使用第三方模型条款</el-checkbox></el-form-item>
                </el-form>
              </div>
            </el-collapse-transition>
          </section>

          <!-- 06 绘制图表 -->
          <section v-show="currentStepIndex === 6" class="settings-block">
            <div class="module-switch-row" @click="toggleChartExpanded">
              <span class="module-switch-label">
                <el-icon class="module-arrow" :class="{ 'is-expanded': chartExpanded }"><ArrowRight /></el-icon>
                绘制图表
              </span>
              <el-switch v-model="settings.chartEnabled" @click.stop @change="val => { if(val) chartExpanded = true; }" />
            </div>
            <el-collapse-transition>
              <div v-show="chartExpanded || settings.chartEnabled" class="module-content">
                <el-form label-position="left" class="compact-form" label-width="140px">
                  <el-form-item label="模型">
                    <AutobiProviderModelSelect
                      :providers="usableProviders"
                      :provider-id="settings.chartProviderId"
                      :model-name="settings.chartModelName"
                      @update:provider-id="settings.chartProviderId = $event"
                      @update:model-name="settings.chartModelName = $event"
                    />
                  </el-form-item>
                  <el-form-item label="采样概率">
                    <el-input-number v-model="settings.chartTopP" :min="0" :max="1" :step="0.1" :precision="1" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="采样数量">
                    <el-input-number v-model="settings.chartTopK" :min="1" :max="200" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="温度">
                    <el-input-number v-model="settings.chartTemperature" :min="0" :max="2" :step="0.1" :precision="1" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="最大输出">
                    <el-input-number v-model="settings.chartMaxOut" :min="256" :max="32768" :step="256" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="最大上下文">
                    <el-input-number v-model="settings.chartMaxCtx" :min="1024" :max="32768" :step="256" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="Prompt">
                    <el-input v-model="settings.chartPrompt" type="textarea" :rows="2" placeholder="系统提示词..." />
                  </el-form-item>
                  <el-form-item><el-checkbox v-model="settings.chartDisclaimer">同意使用第三方模型条款</el-checkbox></el-form-item>
                </el-form>
              </div>
            </el-collapse-transition>
          </section>
        </div>
      </div>

      <template #footer>
        <div class="settings-footer">
          <el-button @click="resetSettingsForm">重置</el-button>
          <el-button type="primary" class="btn-primary-brand" :loading="settingsSaving" @click="handleSettingsSubmit">
            保存配置
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 实验室：全屏弹窗（不离开列表页） -->
    <el-dialog
      v-model="labDialogVisible"
      :title="labDialogTitle"
      fullscreen
      append-to-body
      destroy-on-close
      class="autobi-lab-fullscreen-dialog"
      @closed="onLabDialogClosed"
    >
      <AutobiLaboratoryContent
        v-if="labProjectId != null"
        :key="String(labProjectId)"
        :project-id="labProjectId"
        embedded-in-dialog
        @close="labDialogVisible = false"
      />
    </el-dialog>

    <AutobiApiDocsDialog
      v-model="apiDocsVisible"
      :project-id="apiDocsProjectId"
      :api-access-id="apiDocsAccessId"
      :project-name="apiDocsProjectName"
    />

    <el-dialog
      v-model="cloneDialogVisible"
      title="克隆项目"
      width="480px"
      append-to-body
      class="autobi-dialog"
      @close="resetCloneForm"
    >
      <el-form label-position="top">
        <el-form-item label="目标文件夹" required>
          <el-select v-model="cloneForm.folder_id" placeholder="请选择文件夹" style="width: 100%">
            <el-option v-for="f in folders" :key="f.id" :label="f.name" :value="f.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="新项目名称" required>
          <el-input v-model="cloneForm.name" placeholder="请输入名称" maxlength="255" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cloneDialogVisible = false">取消</el-button>
        <el-button type="primary" class="btn-primary-brand" :loading="cloneLoading" @click="submitClone">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, Download, Search, Folder, MoreFilled, Check, Loading, ArrowRight, Collection, Edit, DataAnalysis, Document, DataLine, Setting, InfoFilled } from '@element-plus/icons-vue'
import AutobiProviderModelSelect from '../components/AutobiProviderModelSelect.vue'
import AutobiLaboratoryContent from '../components/AutobiLaboratoryContent.vue'
import AutobiApiDocsDialog from '../components/AutobiApiDocsDialog.vue'
import { getModelProviders } from '../api/modelProvider'
import knowledgeBaseApi from '../api/knowledgeBase'
import {
  listAutobiFolders,
  createAutobiFolder,
  updateAutobiFolder,
  deleteAutobiFolder,
  moveAutobiFolder,
  listAutobiProjects,
  getAutobiProject,
  exportAutobiProject,
  importAutobiProject,
  createAutobiProject,
  updateAutobiProject,
  deleteAutobiProject
} from '../api/autobi'
import agentAppApi from '../api/agentApp'
import { buildStoredConfig, applyConfigJsonToSettings } from '../utils/autobiPayload'
import { parseLabImportPayload, suggestLabImportName } from '../utils/autobiProjectExport'
import { downloadJson, safeFilenamePart } from '../utils/agentAppExport'
import {
  DEFAULT_CHART_DRAWING_PROMPT,
  DEFAULT_BI_SUMMARY_PROMPT,
  DEFAULT_NL2SQL_PROMPT,
  DEFAULT_KNOWLEDGE_REWRITE_PROMPT,
  DEFAULT_NER_RETRIEVAL_PROMPT
} from '../utils/autobiDefaultPrompts'

const searchKeyword = ref('')
const folders = ref([])
const selectedFolderId = ref(null)
const labImportFileRef = ref(null)
const labImportReading = ref(false)
const labImportVisible = ref(false)
const labImportLoading = ref(false)
const labImportPayload = ref(null)
const labImportFileName = ref('')
const labImportForm = reactive({ folder_id: null, name: '' })
const labExportingIds = reactive(new Set())

function resetLabImport() {
  labImportPayload.value = null
  labImportFileName.value = ''
  labImportForm.folder_id = null
  labImportForm.name = ''
}

async function onLabImportFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || labImportLoading.value || labImportReading.value) return
  resetLabImport()
  labImportReading.value = true
  try {
    const payload = parseLabImportPayload(await file.text())
    labImportPayload.value = payload
    labImportFileName.value = file.name
    labImportForm.folder_id = selectedFolderId.value ?? folders.value[0]?.id ?? null
    labImportForm.name = suggestLabImportName(payload, items.value)
    labImportVisible.value = true
  } catch (e) {
    ElMessage.error('读取实验室配置失败：' + e.message)
  } finally {
    labImportReading.value = false
  }
}

async function submitLabImport() {
  if (labImportLoading.value || !labImportPayload.value) return
  const name = labImportForm.name.trim()
  if (!name || name.length > 255) {
    ElMessage.warning('实验室名称须为 1 至 255 个字符')
    return
  }
  if (labImportForm.folder_id == null) {
    ElMessage.warning('请选择目标文件夹')
    return
  }
  labImportLoading.value = true
  try {
    const imported = await importAutobiProject({ payload: labImportPayload.value, name, folder_id: labImportForm.folder_id })
    selectedFolderId.value = Number(imported.folder_id ?? labImportForm.folder_id)
    searchKeyword.value = ''
    labImportVisible.value = false
    ElMessage.success('导入成功，请在设置中选择模型和知识库')
    await loadData()
  } catch (e) {
    ElMessage.error('导入失败：' + (e.response?.data?.detail || e.message))
  } finally {
    labImportLoading.value = false
  }
}

async function handleLabExport(item) {
  if (labExportingIds.has(item.id)) return
  labExportingIds.add(item.id)
  try {
    const payload = await exportAutobiProject(item.id)
    downloadJson(`${safeFilenamePart(payload.project.name)}-实验室.json`, payload)
    ElMessage.success('导出成功，模型和知识库选择已清空')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.response?.data?.detail || e.message))
  } finally {
    labExportingIds.delete(item.id)
  }
}

const createFolderVisible = ref(false)
const newFolderName = ref('')
const createFolderLoading = ref(false)
const renameFolderVisible = ref(false)
const renameFolderId = ref(null)
const renameFolderName = ref('')
const renameFolderLoading = ref(false)
const settingsFolderId = ref(null)
const labDialogVisible = ref(false)
const labProjectId = ref(null)

const labDialogTitle = computed(() => {
  const id = labProjectId.value
  if (id == null) return '实验中心 · 实验室'
  const item = items.value.find(i => String(i.id) === String(id))
  return item ? `实验室 — ${item.name}` : '实验中心 · 实验室'
})

function onLabDialogClosed() {
  labProjectId.value = null
}

const apiDocsVisible = ref(false)
const apiDocsProjectId = ref(null)
const apiDocsAccessId = ref('')
const apiDocsProjectName = ref('')

function openApiDocs(item) {
  apiDocsProjectId.value = item.id
  apiDocsAccessId.value = item.api_access_id || ''
  apiDocsProjectName.value = item.name || ''
  apiDocsVisible.value = true
}

const cloneDialogVisible = ref(false)
const cloneLoading = ref(false)
const cloneSourceId = ref(null)
const cloneForm = reactive({
  folder_id: null,
  name: ''
})

function openCloneDialog(item) {
  cloneSourceId.value = item.id
  cloneForm.folder_id = selectedFolderId.value
  const base = (item.name || '项目').slice(0, 200)
  cloneForm.name = `${base} 副本`
  cloneDialogVisible.value = true
}

function resetCloneForm() {
  cloneSourceId.value = null
  cloneForm.folder_id = null
  cloneForm.name = ''
}

async function submitClone() {
  const sid = cloneSourceId.value
  const name = (cloneForm.name || '').trim()
  const targetFolderId = cloneForm.folder_id
  if (sid == null) return
  if (targetFolderId == null) {
    ElMessage.warning('请选择目标文件夹')
    return
  }
  if (!name) {
    ElMessage.warning('请输入新项目名称')
    return
  }
  cloneLoading.value = true
  try {
    const detail = await getAutobiProject(sid)
    const cfg =
      detail.config_json && typeof detail.config_json === 'object'
        ? JSON.parse(JSON.stringify(detail.config_json))
        : {}
    const desc = detail.description != null ? String(detail.description) : ''
    const created = await createAutobiProject({
      name,
      description: desc || null,
      folder_id: targetFolderId
    })
    const newId = created?.id
    if (newId == null) {
      throw new Error('创建返回缺少 id')
    }
    await updateAutobiProject(newId, {
      folder_id: targetFolderId,
      config_json: cfg
    })
    ElMessage.success('克隆成功')
    cloneDialogVisible.value = false
    resetCloneForm()
    if (selectedFolderId.value !== targetFolderId) {
      selectedFolderId.value = targetFolderId
    }
    await loadData()
  } catch (e) {
    ElMessage.error('克隆失败：' + (e.response?.data?.detail || e.message))
  } finally {
    cloneLoading.value = false
  }
}

const dialogVisible = ref(false)
const settingsVisible = ref(false)
const settingsTitle = ref('设置')
const settingsSaving = ref(false)
const currentSettingsItem = ref(null)
const formRef = ref(null)
const items = ref([])
const knowledgeBaseList = ref([])
const knowledgeBasesLoading = ref(false)
let listLoadSequence = 0
let settingsLoadSequence = 0

/** 与 buildStoredConfig 合并用：保留 multi_rewrite 等未暴露表单项 */
const requestSnapshot = ref({
  messages: [{ role: 'user', content: '' }],
  stream: false
})
const lastLoadedAdvanced = ref(null)

const form = reactive({
  id: null,
  folder_id: null,
  name: '',
  description: ''
})

const formRules = {
  folder_id: [{ required: true, message: '请选择文件夹', trigger: 'change' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }]
}

const collapseNames = ref(['kb'])
const collapseNames01 = ref(['rewrite'])
const collapseNames02 = ref(['col', 'val', 'sql', 'ner'])
const collapseNames03 = ref(['exec'])
const collapseNames04 = ref(['sum'])
const collapseNames05 = ref(['chart'])

// 步骤进度相关
const currentStepIndex = ref(0)

// 各模块展开状态
const rewriteExpanded = ref(true)
const nerExpanded = ref(true)
const summaryExpanded = ref(true)
const chartExpanded = ref(true)
const sqlPermissionRewriteExpanded = ref(true)

// 召回配置子模块展开状态
const recallColExpanded = ref(true)
const recallValExpanded = ref(true)
const recallSqlExpanded = ref(true)

function toggleRewriteExpanded() { rewriteExpanded.value = !rewriteExpanded.value }
function toggleNerExpanded() { nerExpanded.value = !nerExpanded.value }
function toggleSummaryExpanded() { summaryExpanded.value = !summaryExpanded.value }
function toggleChartExpanded() { chartExpanded.value = !chartExpanded.value }
function toggleSqlPermissionRewriteExpanded() { sqlPermissionRewriteExpanded.value = !sqlPermissionRewriteExpanded.value }
function toggleRecallColExpanded() { recallColExpanded.value = !recallColExpanded.value }
function toggleRecallValExpanded() { recallValExpanded.value = !recallValExpanded.value }
function toggleRecallSqlExpanded() { recallSqlExpanded.value = !recallSqlExpanded.value }

const settingsSteps = computed(() => [
  { id: 'kb', label: '数据准备', completed: !!settings.knowledgeBaseId, disabled: false, icon: 'Collection', desc: '选择数据表类型的知识库，作为SQL生成的检索增强数据来源' },
  { id: 'rewrite', label: '改写配置', completed: settings.rewriteEnabled && settings.rewriteDisclaimer, disabled: !settings.rewriteEnabled, icon: 'Edit', desc: '对用户问题进行知识改写，增强检索效果' },
  { id: 'recall', label: '召回配置', completed: true, disabled: false, icon: 'Search', desc: '配置表/列、值、SQL样例等多路召回策略' },
  { id: 'sql', label: '生成SQL', completed: settings.sqlDisclaimer, disabled: false, icon: 'DataAnalysis', desc: '根据问题、库表信息与参考样例生成可执行SQL' },
  { id: 'sql-permission', label: 'SQL改写', completed: !settings.sqlPermissionRewriteEnabled || (!!settings.sqlPermissionRewriteAgentId && !!settings.sqlPermissionRewriteVersionId), disabled: !settings.sqlPermissionRewriteEnabled, icon: 'DataAnalysis', desc: '生成SQL后调用工作流按权限策略改写SQL' },
  { id: 'summary', label: '总结摘要', completed: settings.summaryEnabled && settings.summaryDisclaimer, disabled: !settings.summaryEnabled, icon: 'Document', desc: '基于SQL查询结果与问题进行总结分析' },
  { id: 'chart', label: '绘制图表', completed: settings.chartEnabled && settings.chartDisclaimer, disabled: !settings.chartEnabled, icon: 'DataLine', desc: '基于查询结果自动选择合适图表并绘制展示' },
])

const iconComponents = {
  Collection,
  Edit,
  Search,
  DataAnalysis,
  Document,
  DataLine,
  Setting,
  InfoFilled,
}

const currentStepIcon = computed(() => iconComponents[settingsSteps.value[currentStepIndex.value]?.icon] || Setting)
const currentStepDesc = computed(() => settingsSteps.value[currentStepIndex.value]?.desc || '')

function goToStep(idx) {
  // Allow clicking any step - completed, current, or future
  currentStepIndex.value = idx
}

function nextStep() {
  if (currentStepIndex.value < settingsSteps.value.length - 1) {
    currentStepIndex.value++
  }
}

const modelProviders = ref([])
const agentApps = ref([])
const agentAppsLoading = ref(false)

function parseModelsStr(modelsStr) {
  if (!modelsStr) return []
  try {
    const parsed = JSON.parse(modelsStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return String(modelsStr)
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
  }
}

/** 仅展示已配置模型列表的供应商（与模型中心数据源一致） */
const usableProviders = computed(() =>
  modelProviders.value.filter(p => parseModelsStr(p.models).length > 0)
)

const selectedSqlPermissionAgent = computed(() =>
  agentApps.value.find(app => Number(app.id) === Number(settings.sqlPermissionRewriteAgentId)) || null
)

const sqlPermissionVersionOptions = computed(() =>
  selectedSqlPermissionAgent.value?.versions || []
)

const selectedSqlPermissionVersion = computed(() =>
  sqlPermissionVersionOptions.value.find(v => Number(v.id) === Number(settings.sqlPermissionRewriteVersionId)) || null
)

function formatSqlPermissionVersionLabel(v) {
  if (!v) return ''
  const status = v.status ? ` · ${v.status}` : ''
  return `${v.name || `版本 #${v.id}`}${status} · ID: ${v.id}`
}

function onSqlPermissionAgentChange() {
  const versions = sqlPermissionVersionOptions.value
  const exists = versions.some(v => Number(v.id) === Number(settings.sqlPermissionRewriteVersionId))
  if (!exists) {
    settings.sqlPermissionRewriteVersionId = versions.find(v => v.is_output)?.id ?? versions[0]?.id ?? null
  }
}

function clearSqlPermissionAgent() {
  settings.sqlPermissionRewriteAgentId = null
  settings.sqlPermissionRewriteVersionId = null
}

function defaultSettings() {
  return {
    knowledgeBaseId: null,
    rewriteEnabled: true,
    keywordRecallEnabled: true,
    rewriteKeywordMaxRecall: 3,
    rewriteProviderId: null,
    rewriteModelName: '',
    rewriteDisclaimer: false,
    rewriteTopP: 0.5,
    rewriteTopK: 3,
    rewriteTemperature: 0.1,
    rewritePrompt: DEFAULT_KNOWLEDGE_REWRITE_PROMPT,
    rewriteMaxOut: 6000,
    rewriteMaxCtx: 4096,
    recallColMax: 15,
    recallColThreshold: 0.3,
    recallValMax: 10,
    recallValThreshold: 0.6,
    recallValMultiColEnabled: false,
    recallValMultiColMax: 10,
    recallValMultiColThreshold: 0.6,
    recallSqlMax: 3,
    recallSqlThreshold: 0,
    nerRetrievalEnabled: false,
    nerRetrievalProviderId: null,
    nerRetrievalModelName: '',
    nerRetrievalDisclaimer: false,
    nerTopP: 0.9,
    nerTopK: 50,
    nerTemperature: 0.3,
    nerPrompt: DEFAULT_NER_RETRIEVAL_PROMPT,
    nerMaxOut: 2048,
    nerMaxCtx: 4096,
    sqlProviderId: null,
    sqlModelName: '',
    sqlDisclaimer: false,
    sqlTopP: 0.3,
    sqlTopK: 50,
    sqlTemperature: 0.3,
    sqlPrompt: DEFAULT_NL2SQL_PROMPT,
    sqlMaxOut: 5120,
    sqlMaxCtx: 4096,
    sqlPermissionRewriteEnabled: false,
    sqlPermissionRewriteAgentId: null,
    sqlPermissionRewriteVersionId: null,
    summaryEnabled: true,
    summaryProviderId: null,
    summaryModelName: '',
    summaryDisclaimer: false,
    summaryTopP: 0.8,
    summaryTopK: 50,
    summaryTemperature: 0.1,
    summaryPrompt: DEFAULT_BI_SUMMARY_PROMPT,
    summaryMaxOut: 5120,
    summaryMaxCtx: 4096,
    chartEnabled: true,
    chartProviderId: null,
    chartModelName: '',
    chartDisclaimer: false,
    chartTopP: 0.8,
    chartTopK: 50,
    chartTemperature: 0.1,
    chartPrompt: DEFAULT_CHART_DRAWING_PROMPT,
    chartMaxOut: 5120,
    chartMaxCtx: 4096
  }
}

const settings = reactive(defaultSettings())

const rewriteModelSelectInvalid = computed(
  () =>
    settings.rewriteEnabled &&
    (!settings.rewriteProviderId || !settings.rewriteModelName)
)

const sqlModelSelectInvalid = computed(
  () => !settings.sqlProviderId || !settings.sqlModelName
)

const nerModelSelectInvalid = computed(
  () =>
    settings.nerRetrievalEnabled &&
    (!settings.nerRetrievalProviderId || !settings.nerRetrievalModelName)
)

const summaryModelSelectInvalid = computed(
  () =>
    settings.summaryEnabled &&
    (!settings.summaryProviderId || !settings.summaryModelName)
)

const chartModelSelectInvalid = computed(
  () =>
    settings.chartEnabled &&
    (!settings.chartProviderId || !settings.chartModelName)
)

const sqlPermissionRewriteInvalid = computed(
  () =>
    settings.sqlPermissionRewriteEnabled &&
    (!settings.sqlPermissionRewriteAgentId || !settings.sqlPermissionRewriteVersionId)
)

const filteredItems = computed(() => {
  if (!searchKeyword.value) return items.value
  const keyword = searchKeyword.value.toLowerCase()
  return items.value.filter(
    item =>
      item.name.toLowerCase().includes(keyword) ||
      (item.description && item.description.toLowerCase().includes(keyword))
  )
})

const formatDate = dateStr => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${d} ${h}:${min}`
}

function cloneJson(obj) {
  return obj == null ? obj : JSON.parse(JSON.stringify(obj))
}

function normalizeRequestSnapshot(req) {
  const r = req && typeof req === 'object' ? req : {}
  const msgs = Array.isArray(r.messages) ? r.messages : []
  return {
    messages:
      msgs.length > 0
        ? cloneJson(msgs)
        : [{ role: 'user', content: '' }],
    stream: r.stream === true
  }
}

async function loadFolders() {
  try {
    const data = await listAutobiFolders()
    folders.value = Array.isArray(data) ? data : []
    if (folders.value.length === 0) {
      selectedFolderId.value = null
      return
    }
    const exists =
      selectedFolderId.value != null &&
      folders.value.some(f => Number(f.id) === Number(selectedFolderId.value))
    if (!exists) {
      selectedFolderId.value = folders.value[0].id
    }
  } catch (e) {
    folders.value = []
    selectedFolderId.value = null
    ElMessage.error('加载文件夹失败：' + (e.response?.data?.detail || e.message))
  }
}

function onSelectFolder(id) {
  settingsLoadSequence += 1
  selectedFolderId.value = id
  loadData()
}

function openCreateFolderDialog() {
  newFolderName.value = ''
  createFolderVisible.value = true
}

async function submitCreateFolder() {
  const name = newFolderName.value.trim()
  if (!name) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  createFolderLoading.value = true
  try {
    const row = await createAutobiFolder({ name })
    ElMessage.success('文件夹已创建')
    createFolderVisible.value = false
    await loadFolders()
    if (row && row.id != null) {
      selectedFolderId.value = row.id
      await loadData()
    }
  } catch (e) {
    ElMessage.error('创建失败：' + (e.response?.data?.detail || e.message))
  } finally {
    createFolderLoading.value = false
  }
}

function openRenameFolderDialog(f) {
  renameFolderId.value = f.id
  renameFolderName.value = f.name || ''
  renameFolderVisible.value = true
}

async function submitRenameFolder() {
  const name = renameFolderName.value.trim()
  if (!name) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  const fid = renameFolderId.value
  if (fid == null) return
  renameFolderLoading.value = true
  try {
    await updateAutobiFolder(fid, { name })
    ElMessage.success('名称已更新')
    renameFolderVisible.value = false
    await loadFolders()
    await loadData()
  } catch (e) {
    ElMessage.error('修改失败：' + (e.response?.data?.detail || e.message))
  } finally {
    renameFolderLoading.value = false
  }
}

async function handleFolderMove(f, direction) {
  try {
    await moveAutobiFolder(f.id, { direction })
    await loadFolders()
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '移动失败')
  }
}

function handleFolderDelete(f) {
  if (f.is_system) {
    ElMessage.warning('系统默认文件夹不可删除')
    return
  }
  ElMessageBox.confirm(`确定删除文件夹「${f.name}」吗？其中的实验中心项目将移动到默认文件夹。`, '提示', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消'
  })
    .then(async () => {
      try {
        const sid = selectedFolderId.value
        await deleteAutobiFolder(f.id)
        ElMessage.success('已删除')
        await loadFolders()
        if (sid === f.id) {
          selectedFolderId.value = folders.value[0]?.id ?? null
        }
        await loadData()
      } catch (e) {
        ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
      }
    })
    .catch(() => {})
}

async function loadData() {
  const sequence = ++listLoadSequence
  const folderId = selectedFolderId.value
  if (folderId == null) {
    items.value = []
    return
  }
  try {
    const data = await listAutobiProjects({ folder_id: folderId })
    if (sequence !== listLoadSequence || folderId !== selectedFolderId.value) return
    items.value = Array.isArray(data) ? data : []
  } catch (e) {
    if (sequence !== listLoadSequence || folderId !== selectedFolderId.value) return
    items.value = []
    ElMessage.error('加载项目列表失败：' + (e.response?.data?.detail || e.message))
  }
}

async function loadKnowledgeBases() {
  knowledgeBasesLoading.value = true
  try {
    const res = await knowledgeBaseApi.getKnowledgeBaseList()
    knowledgeBaseList.value = Array.isArray(res) ? res : []
  } catch (e) {
    knowledgeBaseList.value = []
    ElMessage.warning('加载知识库列表失败：' + (e.response?.data?.detail || e.message))
  } finally {
    knowledgeBasesLoading.value = false
  }
}

function handleAdd() {
  form.id = null
  form.folder_id = selectedFolderId.value
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

async function openSettings(item) {
  if (settingsSaving.value) return
  const sequence = ++settingsLoadSequence
  currentSettingsItem.value = null
  settingsVisible.value = false

  const tasks = []
  if (!modelProviders.value.length) tasks.push(loadModelProviders())
  if (!knowledgeBaseList.value.length) tasks.push(loadKnowledgeBases())
  if (!folders.value.length) tasks.push(loadFolders())
  if (!agentApps.value.length) tasks.push(loadAgentApps())
  let detail
  try {
    // 每次编辑都读取最新配置，避免旧详情覆盖此前已保存的修改。
    const [latestDetail] = await Promise.all([getAutobiProject(item.id), ...tasks])
    detail = latestDetail
  } catch (e) {
    if (sequence === settingsLoadSequence) {
      ElMessage.error('加载项目配置失败：' + (e.response?.data?.detail || e.message))
    }
    return
  }
  if (sequence !== settingsLoadSequence) return

  currentSettingsItem.value = detail
  settingsTitle.value = `设置 — ${detail.name}`
  currentStepIndex.value = 0
  Object.assign(settings, defaultSettings())
  settingsFolderId.value = Number(detail.folder_id ?? item.folder_id ?? selectedFolderId.value)
  const cfg = detail.config_json && typeof detail.config_json === 'object' ? detail.config_json : {}
  applyConfigJsonToSettings(cfg, settings)
  const req = cfg.request
  requestSnapshot.value = normalizeRequestSnapshot(req)
  lastLoadedAdvanced.value =
    req?.advanced_config && typeof req.advanced_config === 'object'
      ? cloneJson(req.advanced_config)
      : null

  // 数据就绪后才显示弹窗，避免闪烁
  settingsVisible.value = true
}

function openLaboratory(item) {
  settingsLoadSequence += 1
  labProjectId.value = item.id
  labDialogVisible.value = true
}

async function loadModelProviders() {
  try {
    const data = await getModelProviders()
    if (Array.isArray(data)) {
      modelProviders.value = data
    } else if (data && Array.isArray(data.items)) {
      modelProviders.value = data.items
    } else if (data && Array.isArray(data.list)) {
      modelProviders.value = data.list
    } else {
      modelProviders.value = []
    }
  } catch {
    modelProviders.value = []
    ElMessage.warning('加载模型供应商失败，请确认已登录且模型中心可用')
  }
}

async function loadAgentApps() {
  agentAppsLoading.value = true
  try {
    const data = await agentAppApi.listAgentApps({ page: 1, page_size: 200 })
    const rows = Array.isArray(data) ? data : (data?.items || data?.list || [])
    const detailRows = await Promise.all(
      rows.map(async app => {
        try {
          return await agentAppApi.getAgentApp(app.id)
        } catch {
          return app
        }
      })
    )
    agentApps.value = detailRows
  } catch (e) {
    agentApps.value = []
    ElMessage.warning('加载工作流列表失败：' + (e.response?.data?.detail || e.message))
  } finally {
    agentAppsLoading.value = false
  }
}

function resetSettingsForm() {
  Object.assign(settings, defaultSettings())
  requestSnapshot.value = normalizeRequestSnapshot(null)
  lastLoadedAdvanced.value = null
  ElMessage.success('已恢复默认配置（提交前可再次调整）')
}

async function handleSettingsSubmit() {
  if (settingsSaving.value) return
  if (!settings.knowledgeBaseId) {
    ElMessage.warning('请选择关联知识库')
    return
  }
  if (rewriteModelSelectInvalid.value) {
    ElMessage.warning('改写配置：请选择系统模型（供应商 + 模型）')
    return
  }
  if (sqlModelSelectInvalid.value) {
    ElMessage.warning('生成SQL配置：请选择系统模型')
    return
  }
  if (nerModelSelectInvalid.value) {
    ElMessage.warning('NER 召回：开启后请选择系统模型（供应商 + 模型）')
    return
  }
  if (summaryModelSelectInvalid.value) {
    ElMessage.warning('总结摘要：请选择系统模型')
    return
  }
  if (chartModelSelectInvalid.value) {
    ElMessage.warning('绘制图表：请选择系统模型')
    return
  }
  if (sqlPermissionRewriteInvalid.value) {
    ElMessage.warning('SQL 权限改写：开启后请选择工作流 ID 和版本')
    return
  }
  if (settings.rewriteEnabled && !settings.rewriteDisclaimer) {
    ElMessage.warning('知识改写：请勾选「我已阅读并同意…」后再提交')
    return
  }
  if (settings.nerRetrievalEnabled && !settings.nerRetrievalDisclaimer) {
    ElMessage.warning('NER 召回：请勾选用户协议后再提交')
    return
  }
  if (!settings.sqlDisclaimer) {
    ElMessage.warning('生成 SQL：请勾选用户协议后再提交')
    return
  }
  if (settings.summaryEnabled && !settings.summaryDisclaimer) {
    ElMessage.warning('总结摘要：请勾选用户协议后再提交')
    return
  }
  if (settings.chartEnabled && !settings.chartDisclaimer) {
    ElMessage.warning('绘制图表：请勾选用户协议后再提交')
    return
  }

  const pid = currentSettingsItem.value?.id
  if (!pid) {
    ElMessage.error('未找到项目 ID')
    return
  }
  if (settingsFolderId.value == null) {
    ElMessage.warning('请选择所属文件夹')
    return
  }

  settingsSaving.value = true
  try {
    const targetFolderId = settingsFolderId.value
    const configJson = buildStoredConfig(
      settings,
      requestSnapshot.value,
      lastLoadedAdvanced.value
    )
    const saved = await updateAutobiProject(pid, {
      folder_id: targetFolderId,
      config_json: configJson
    })
    selectedFolderId.value = Number(saved.folder_id ?? targetFolderId)
    lastLoadedAdvanced.value = cloneJson(configJson.request?.advanced_config) ?? null
    ElMessage.success('配置已保存')
    settingsVisible.value = false
    await loadData()
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    settingsSaving.value = false
  }
}

function handleDelete(item) {
  ElMessageBox.confirm(`确定要删除「${item.name}」吗？`, '提示', {
    type: 'warning',
    confirmButtonText: '确定',
    cancelButtonText: '取消'
  })
    .then(async () => {
      try {
        await deleteAutobiProject(item.id)
        ElMessage.success('已删除')
        await loadData()
      } catch (e) {
        ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
      }
    })
    .catch(() => {})
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  try {
    const created = await createAutobiProject({
      name: form.name,
      description: form.description || null,
      folder_id: form.folder_id
    })
    selectedFolderId.value = Number(created.folder_id ?? form.folder_id)
    ElMessage.success('创建成功')
    dialogVisible.value = false
    await loadData()
  } catch (e) {
    ElMessage.error('创建失败：' + (e.response?.data?.detail || e.message))
  }
}

function resetForm() {
  form.id = null
  form.folder_id = selectedFolderId.value
  form.name = ''
  form.description = ''
  formRef.value?.clearValidate()
}

onMounted(async () => {
  await Promise.all([loadFolders(), loadModelProviders(), loadKnowledgeBases(), loadAgentApps()])
  await loadData()
})
</script>

<style scoped>
/* 页面撑满主内容区，文件夹栏与卡片列表分别管理滚动。 */
.autobi-page {
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.autobi-page > .page-header {
  flex-shrink: 0;
}

.autobi-body {
  display: flex;
  align-items: stretch;
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.folder-aside {
  width: 168px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-self: stretch;
  min-height: 0;
  border-right: 1px solid #e4e7ed;
  background: #f7f8fa;
}

.folder-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 0;
}

.folder-row {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 6px 6px 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #303133;
  transition: background 0.15s;
}

.folder-row:hover {
  background: rgba(31, 184, 204, 0.08);
}

.folder-row.is-active {
  background: #e9f8fa;
  color: #1fb8cc;
  font-weight: 500;
}

.folder-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.folder-more-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #909399;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.folder-more-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #606266;
}

.folder-row.is-active .folder-more-btn {
  color: #1fb8cc;
}

.folder-item-icon {
  flex-shrink: 0;
}

.folder-item-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-footer {
  flex-shrink: 0;
}

.folder-create-btn {
  margin: 12px;
  width: calc(100% - 24px);
}

.sql-agent-picker {
  width: 100%;
  min-width: 0;
}

.sql-agent-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;
  background: linear-gradient(180deg, #ffffff 0%, var(--el-color-primary-light-9) 100%);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.sql-agent-card__icon {
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary-dark-2);
  font-size: 14px;
  font-weight: 700;
}

.sql-agent-card__main {
  flex: 1;
  min-width: 0;
}

.sql-agent-card__title,
.sql-agent-card__desc,
.sql-agent-card__meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sql-agent-card__title {
  color: #1f2d3d;
  font-size: 14px;
  font-weight: 700;
}

.sql-agent-card__desc {
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
}

.sql-agent-card__meta {
  margin-top: 5px;
  color: var(--el-color-primary-dark-2);
  font-size: 12px;
}

.sql-permission-hint {
  margin: 2px 0 0 140px;
  color: #7a8794;
  font-size: 12px;
  line-height: 1.6;
}

.autobi-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  container-type: inline-size;
  background: #fff;
}

.page-tabs {
  display: flex;
  gap: 32px;
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
  padding: 0 8px;
  margin: 0 -24px 0;
  padding-left: 24px;
}

.tab-item {
  padding: 14px 4px;
  font-size: 16px;
  color: #606266;
  cursor: default;
  position: relative;
}

.tab-item.is-active {
  color: var(--el-color-primary);
  font-weight: 600;
}

.tab-item.is-active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 3px;
  background: var(--el-color-primary);
  border-radius: 2px 2px 0 0;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  padding: 16px 20px;
  gap: 12px;
  background-color: #fff;
  flex-shrink: 0;
}

.toolbar > .el-button {
  flex-shrink: 0;
  margin-left: 0;
}

.toolbar-spacer {
  flex: 1;
}

.btn-add {

  padding: 10px 20px;
  font-weight: 500;
}

.search-input {
  width: 280px;
  max-width: 100%;
}

.search-input :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.card-list {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  /* 滚动由外层承接；行高始终容纳全部操作，避免可用高度挤压卡片。 */
  grid-auto-rows: max-content;
  align-items: stretch;
  gap: 20px;
  padding: 4px 20px 20px;
  background-color: #fff;
}

@container (max-width: 1080px) {
  .card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@container (max-width: 720px) {
  .card-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@container (max-width: 560px) {
  .toolbar-spacer {
    display: none;
  }

  .search-input {
    width: 100%;
  }
}

.autobi-card {
  min-width: 0;
  background: #fff;
  border: 1px solid #ebeef2;
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-sizing: border-box;
}

.autobi-card > * {
  flex-shrink: 0;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.card-logo-wrap {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: #f2f3f5;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.card-logo-img {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.card-meta {
  flex: 1;
  min-width: 0;
}

.card-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-time {
  margin: 0;
  font-size: 12px;
  color: #86909c;
  line-height: 1.5;
}

.card-icon-btn {
  border: none;
  background: none;
  padding: 6px;
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  color: #909399;
  flex-shrink: 0;
  transition: background 0.2s, color 0.2s;
}
.card-delete-btn:hover { background: #fff1f0; color: #f56c6c; }

.card-desc-box {
  background: #f7f8fa;
  border-radius: 8px;
  padding: 8px 10px;
  overflow: hidden;
}
.card-desc {
  margin: 0;
  font-size: 13px;
  color: #4e5969;
  line-height: 1.45;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-api-box {
  background: #f7f8fa;
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.card-api-label { flex-shrink: 0; font-size: 13px; color: #4e5969; font-weight: 500; }
.card-api-value {
  min-width: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  background: #e5e6eb;
  padding: 2px 8px;
  border-radius: 4px;
  color: #1d2129;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-api-hint { font-size: 12px; color: #86909c; flex-shrink: 0; }

.card-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-top: auto;
  flex-shrink: 0;
}

.action-btn {
  min-width: 0;
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 7px 4px;
  border-radius: 8px;
  border: none;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
  cursor: pointer;
  transition: opacity 0.2s;
}
.action-btn > svg,
.action-btn > .el-icon { flex-shrink: 0; }
.action-btn:focus-visible,
.card-icon-btn:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
.action-btn:hover { opacity: 0.85; }
.action-btn:disabled { cursor: wait; opacity: 0.6; }
.lab-export-btn { grid-column: 1 / -1; }
.lab-import-filename { color: #606266; overflow-wrap: anywhere; }

.action-lab {
  background: #e9f8fa;
  color: #1fb8cc;
}
.action-default {
  background: #f2f3f5;
  color: #4e5969;
}

.btn-primary-brand {
}

/* 设置弹窗 */
.settings-body {
  max-height: min(72vh, 720px);
  overflow-y: auto;
  padding-right: 8px;
}

.settings-block {
  margin-bottom: 28px;
}

.settings-block:last-child {
  margin-bottom: 8px;
}

.block-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.block-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  padding: 0 8px;
  border-radius: 6px;
  background: linear-gradient(135deg, var(--el-color-primary-light-9), var(--el-color-primary-light-8));
  color: var(--el-color-primary);
  font-weight: 700;
  font-size: 14px;
}

.block-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.sub-section {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.sub-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.sub-section-title {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}

.model-select-wrap {
  margin-top: 8px;
  width: 100%;
}

.error-text {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-color-danger);
  line-height: 1.4;
}

.field-hint.warn {
  color: var(--el-color-warning);
}

.settings-collapse {
  border: none;
  --el-collapse-header-bg-color: #fafafa;
}

.settings-collapse :deep(.el-collapse-item__header) {
  font-weight: 500;
  padding-left: 12px;
}

.settings-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.settings-collapse :deep(.el-collapse-item__content) {
  padding: 12px 12px 16px;
}

.collapse-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 12px;
}

.collapse-switch {
  margin-left: auto;
}

.block-desc {
  margin: 0 0 12px;
}

.inner-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: #303133;
}

.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.disclaimer-check {
  margin-top: 10px;
  align-items: flex-start;
  white-space: normal;
  line-height: 1.5;
}

/* Prompt：默认较矮，内容多时框内滚动 */
.prompt-textarea {
  width: 100%;
}

.prompt-textarea :deep(.el-textarea__inner) {
  min-height: 72px;
  max-height: 280px;
  overflow-y: auto;
  line-height: 1.5;
  resize: vertical;
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

/* 步骤条 - 简洁专业风格 */
.settings-steps-bar {
  display: flex;
  align-items: stretch;
  justify-content: flex-start;
  padding: 0;
  background: #fff;
  border-radius: 12px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  border: 1px solid #e4e7ed;
  overflow-x: auto;
  overflow-y: hidden;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1 0 132px;
  justify-content: center;
  min-width: 132px;
  padding: 14px 18px;
  cursor: pointer;
  position: relative;
  transition: all 0.2s ease;
  border-right: 1px solid #e4e7ed;
}

.step-item:last-child {
  border-right: none;
}

.step-item:hover {
  background: var(--el-color-primary-light-9);
}

.step-item.is-active {
  background: linear-gradient(135deg, var(--el-color-primary) 0%, var(--el-color-primary-dark-2) 100%);
  color: #fff;
}

.step-item.is-active .step-dot {
  background: rgba(255,255,255,0.25);
  border-color: rgba(255,255,255,0.5);
  color: #fff;
}

.step-item.is-active .step-dot span {
  color: #fff;
}

.step-item.is-active .step-dot :deep(.el-icon) {
  color: #fff;
}

.step-item.is-active .step-title {
  color: #fff;
  font-weight: 600;
}

/* When a step is both done AND active, active style takes priority */
.step-item.is-active.is-done .step-dot {
  background: rgba(255,255,255,0.25);
  border-color: rgba(255,255,255,0.5);
  color: #fff;
}

.step-item.is-active.is-done .step-title {
  color: #fff;
}

.step-item.is-done .step-dot {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}

.step-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f0f2f5;
  border: 1.5px solid #dcdfe6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.step-title {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.step-item.is-done .step-title {
  color: var(--el-color-primary-dark-2);
}

.step-item.is-done:hover .step-title {
  color: var(--el-color-primary);
}

/* 功能关闭时的置灰状态 */
.step-item.is-disabled {
  opacity: 0.42;
  cursor: default;
}

.step-item.is-disabled .step-dot {
  background: #e8e9eb;
  border-color: #dcdfe6;
  color: #c0c4cc;
}

.step-item.is-disabled .step-title {
  color: #c0c4cc;
}

/* 模块描述 */
.settings-module-desc {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f4fcfd 0%, #e9f8fa 100%);
  border-radius: 8px;
  margin-bottom: 16px;
  color: #606266;
  font-size: 13px;
  border-left: 3px solid var(--el-color-primary);
}

.settings-module-desc .el-icon {
  color: var(--el-color-primary);
  font-size: 16px;
  flex-shrink: 0;
}

/* 内容区固定高度，可滚动 */
.settings-content-wrap {
  height: 420px;
  overflow: hidden;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  background: #fafafa;
}

.settings-body {
  height: 100%;
  overflow-y: auto;
  padding: 16px;
}

.settings-body::-webkit-scrollbar {
  width: 6px;
}

.settings-body::-webkit-scrollbar-track {
  background: #f0f0f0;
  border-radius: 3px;
}

.settings-body::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}

.settings-body::-webkit-scrollbar-thumb:hover {
  background: #a0a4ae;
}

.settings-block {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e4e7ed;
  margin-bottom: 12px;
  overflow: hidden;
}

.settings-block:last-child {
  margin-bottom: 0;
}

.compact-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.compact-form :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

.compact-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: #303133;
  font-size: 13px;
}

.compact-form :deep(.el-input-number) {
  width: 100%;
}

.compact-form :deep(.el-slider) {
  width: 100%;
}

.module-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: linear-gradient(135deg, #f4fcfd 0%, #e9f8fa 100%);
  cursor: pointer;
  transition: background 0.2s;
}

.module-switch-row:hover {
  background: linear-gradient(135deg, #e9f8fa 0%, #d2f1f5 100%);
}

.module-switch-label {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.module-arrow {
  transition: transform 0.2s;
  color: #909399;
  font-size: 12px;
}

.module-arrow.is-expanded {
  transform: rotate(90deg);
}

.module-content {
  padding: 16px;
  background: #fff;
}

.ner-switch {
  margin: 0 -16px;
  padding: 14px 16px;
  background: #f4fcfd;
  border-top: 1px solid #e4e7ed;
  border-bottom: 1px solid #e4e7ed;
}

.module-content :deep(.el-form-item) {
  margin-bottom: 14px;
}

/* 召回子模块样式 */
.sub-module {
  border-bottom: 1px solid #e4e7ed;
}

.sub-module:last-child {
  border-bottom: none;
}

.sub-module-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  background: #fafbfc;
  transition: background 0.2s;
}

.sub-module-header:hover {
  background: var(--el-color-primary-light-9);
}

.sub-module-title {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.sub-module-arrow {
  transition: transform 0.2s;
  color: #909399;
  font-size: 12px;
}

.sub-module-arrow.is-expanded {
  transform: rotate(90deg);
}

.sub-module-content {
  padding: 14px 16px;
  background: #fff;
}
</style>

<style>
.autobi-settings-dialog .el-dialog__body {
  padding: 16px 20px 12px;
}

/* 实验室全屏弹窗：内容区撑满，内嵌 AutobiLaboratoryContent */
.autobi-lab-fullscreen-dialog.el-dialog {
  display: flex;
  flex-direction: column;
  margin: 0 !important;
  height: 100vh;
  max-height: 100vh;
  border-radius: 0;
}

.autobi-lab-fullscreen-dialog .el-dialog__header {
  flex-shrink: 0;
  margin-right: 0;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.autobi-lab-fullscreen-dialog .el-dialog__body {
  flex: 1;
  padding: 0 !important;
  overflow: hidden;
  min-height: 0;
}
</style>
