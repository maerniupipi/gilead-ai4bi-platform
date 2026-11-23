-- AI4BI Platform schema; generated from current SQLAlchemy models.

-- Empty tables only. Use scripts/init_database.py for generic initial data.

SET NAMES utf8mb4;

SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE IF NOT EXISTS agent_app_call_logs (
	id INTEGER NOT NULL AUTO_INCREMENT,
	agent_app_id INTEGER NOT NULL,
	version_id INTEGER,
	caller VARCHAR(64),
	conversation_id VARCHAR(128),
	request_text TEXT,
	status VARCHAR(32) NOT NULL,
	output_preview TEXT,
	error_message TEXT,
	elapsed_ms INTEGER NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_agent_app_call_logs_agent_app_id ON agent_app_call_logs (agent_app_id);

CREATE INDEX ix_agent_app_call_logs_id ON agent_app_call_logs (id);

CREATE INDEX ix_agent_app_call_logs_version_id ON agent_app_call_logs (version_id);

CREATE TABLE IF NOT EXISTS agent_app_folders (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(128) NOT NULL,
	sort_order INTEGER NOT NULL DEFAULT '0',
	is_system BOOL NOT NULL DEFAULT '0',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_agent_app_folders_id ON agent_app_folders (id);

CREATE INDEX ix_agent_app_folders_space_id ON agent_app_folders (space_id);

CREATE TABLE IF NOT EXISTS agent_workflow_traces (
	id INTEGER NOT NULL AUTO_INCREMENT,
	trace_id VARCHAR(36) NOT NULL COMMENT 'UUID 追踪ID',
	run_id VARCHAR(36) NOT NULL COMMENT '运行ID',
	app_id INTEGER NOT NULL COMMENT '应用ID',
	version_id INTEGER COMMENT '版本ID',
	app_name VARCHAR(128) COMMENT '应用名称(冗余)',
	parent_trace_id VARCHAR(36) COMMENT '父级 trace_id（嵌套工作流）',
	status VARCHAR(32) NOT NULL COMMENT 'running|done|error',
	steps JSON NOT NULL COMMENT '节点执行步骤数组',
	nodes JSON COMMENT '工作流节点定义快照',
	edges JSON COMMENT '工作流边定义快照',
	output TEXT COMMENT '最终输出',
	error TEXT COMMENT '错误信息',
	elapsed_ms INTEGER NOT NULL COMMENT '总耗时(ms)',
	created_at BIGINT NOT NULL COMMENT '创建时间(epoch ms)',
	updated_at BIGINT NOT NULL COMMENT '更新时间(epoch ms)',
	db_created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	db_updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_agent_workflow_traces_app_id ON agent_workflow_traces (app_id);

CREATE INDEX ix_agent_workflow_traces_created_at ON agent_workflow_traces (created_at);

CREATE INDEX ix_agent_workflow_traces_parent_trace_id ON agent_workflow_traces (parent_trace_id);

CREATE INDEX ix_agent_workflow_traces_run_id ON agent_workflow_traces (run_id);

CREATE UNIQUE INDEX ix_agent_workflow_traces_trace_id ON agent_workflow_traces (trace_id);

CREATE TABLE IF NOT EXISTS audit_logs (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id INTEGER COMMENT '操作用户ID',
	username VARCHAR(64) COMMENT '用户名',
	action VARCHAR(50) NOT NULL COMMENT '操作类型: login/create/update/delete/export',
	resource_type VARCHAR(50) NOT NULL COMMENT '资源类型: user/space/knowledge_base/agent_app等',
	resource_id VARCHAR(100) COMMENT '资源ID',
	resource_name VARCHAR(200) COMMENT '资源名称/描述',
	space_id INTEGER COMMENT '操作所在空间ID',
	ip_address VARCHAR(50) COMMENT 'IP地址',
	method VARCHAR(10) NOT NULL COMMENT 'HTTP方法',
	path VARCHAR(500) NOT NULL COMMENT '请求路径',
	status_code INTEGER COMMENT '响应状态码',
	request_body TEXT COMMENT '请求体（脱敏后）',
	response_body TEXT COMMENT '响应体',
	duration_ms INTEGER COMMENT '请求耗时（毫秒）',
	error_message TEXT COMMENT '错误信息',
	created_at TIMESTAMP NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX idx_audit_logs_action ON audit_logs (action);

CREATE INDEX idx_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX idx_audit_logs_resource_type ON audit_logs (resource_type);

CREATE INDEX idx_audit_logs_space_id ON audit_logs (space_id);

CREATE INDEX idx_audit_logs_user_id ON audit_logs (user_id);

CREATE INDEX ix_audit_logs_id ON audit_logs (id);

CREATE TABLE IF NOT EXISTS autobi_folders (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(128) NOT NULL,
	sort_order INTEGER NOT NULL DEFAULT '0',
	is_system BOOL NOT NULL DEFAULT '0',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_autobi_folders_id ON autobi_folders (id);

CREATE INDEX ix_autobi_folders_space_id ON autobi_folders (space_id);

CREATE TABLE IF NOT EXISTS autobi_lab_traces (
	id INTEGER NOT NULL AUTO_INCREMENT,
	trace_id VARCHAR(36) NOT NULL COMMENT 'UUID 追踪ID',
	project_id VARCHAR(20) NOT NULL COMMENT '实验室项目ID',
	project_name VARCHAR(200) COMMENT '实验室项目名称',
	user_message TEXT NOT NULL COMMENT '用户输入的问题',
	knowledge_base_id INTEGER COMMENT '知识库ID',
	steps JSON NOT NULL COMMENT '18步流水线状态数组',
	created_at BIGINT NOT NULL COMMENT '创建时间(epoch ms)',
	updated_at BIGINT NOT NULL COMMENT '更新时间(epoch ms)',
	db_created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	db_updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_autobi_lab_traces_created_at ON autobi_lab_traces (created_at);

CREATE INDEX ix_autobi_lab_traces_project_id ON autobi_lab_traces (project_id);

CREATE UNIQUE INDEX ix_autobi_lab_traces_trace_id ON autobi_lab_traces (trace_id);

CREATE TABLE IF NOT EXISTS chatbi_api_keys (
	id VARCHAR(36) NOT NULL,
	name VARCHAR(100) NOT NULL,
	environment VARCHAR(8) NOT NULL,
	key_hash VARCHAR(64) NOT NULL,
	key_hint VARCHAR(32) NOT NULL,
	enabled BOOL NOT NULL,
	runtime VARCHAR(128),
	created_at INTEGER NOT NULL,
	updated_at INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (key_hash)
);

CREATE INDEX ix_chatbi_api_keys_environment ON chatbi_api_keys (environment);

CREATE TABLE IF NOT EXISTS chatbi_conversation_contexts (
	conversation_id VARCHAR(36) NOT NULL,
	key_id VARCHAR(36),
	user_id VARCHAR(320),
	attribution_source VARCHAR(24) NOT NULL,
	updated_at INTEGER NOT NULL,
	PRIMARY KEY (conversation_id)
);

CREATE INDEX ix_chatbi_conversation_contexts_key_id ON chatbi_conversation_contexts (key_id);

CREATE INDEX ix_chatbi_conversation_contexts_user_id ON chatbi_conversation_contexts (user_id);

CREATE TABLE IF NOT EXISTS chatbi_conversations (
	id VARCHAR(36) NOT NULL,
	owner VARCHAR(64) NOT NULL,
	runtime VARCHAR(128) NOT NULL,
	active_task VARCHAR(36),
	turn_count INTEGER NOT NULL,
	created_at INTEGER NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_chatbi_conversations_owner ON chatbi_conversations (owner);

CREATE TABLE IF NOT EXISTS chatbi_diagnostic_index_states (
	message_id VARCHAR(36) NOT NULL,
	updated_at BIGINT NOT NULL,
	PRIMARY KEY (message_id)
);

CREATE TABLE IF NOT EXISTS chatbi_exports (
	id VARCHAR(36) NOT NULL,
	file_id VARCHAR(36) NOT NULL,
	owner VARCHAR(64) NOT NULL,
	user_id VARCHAR(320) NOT NULL,
	conversation_id VARCHAR(36) NOT NULL,
	kind VARCHAR(8) NOT NULL,
	summary_type VARCHAR(32),
	payload JSON NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	idempotency_key VARCHAR(128),
	status VARCHAR(16) NOT NULL,
	error TEXT,
	file_name VARCHAR(256) NOT NULL,
	file_size INTEGER NOT NULL,
	created_at INTEGER NOT NULL,
	started_at INTEGER,
	finished_at INTEGER,
	expires_at INTEGER,
	lease_until INTEGER,
	PRIMARY KEY (id),
	CONSTRAINT uq_chatbi_export_request UNIQUE (owner, idempotency_key),
	UNIQUE (file_id)
);

CREATE INDEX ix_chatbi_exports_conversation_id ON chatbi_exports (conversation_id);

CREATE INDEX ix_chatbi_exports_owner ON chatbi_exports (owner);

CREATE INDEX ix_chatbi_exports_status ON chatbi_exports (status);

CREATE TABLE IF NOT EXISTS chatbi_message_diagnostics (
	message_id VARCHAR(36) NOT NULL,
	request_id VARCHAR(64),
	request JSON NOT NULL,
	execution JSON NOT NULL,
	invocations JSON NOT NULL,
	traces JSON NOT NULL,
	updated_at BIGINT NOT NULL,
	PRIMARY KEY (message_id)
);

CREATE INDEX ix_chatbi_message_diagnostics_request_id ON chatbi_message_diagnostics (request_id);

CREATE TABLE IF NOT EXISTS chatbi_messages (
	id VARCHAR(36) NOT NULL,
	conversation_id VARCHAR(36) NOT NULL,
	owner VARCHAR(64) NOT NULL,
	task_id VARCHAR(36) NOT NULL,
	sequence INTEGER NOT NULL,
	query TEXT NOT NULL,
	answer TEXT NOT NULL,
	content JSON NOT NULL,
	status VARCHAR(16) NOT NULL,
	stop_requested BOOL NOT NULL,
	error TEXT,
	created_at INTEGER NOT NULL,
	finished_at INTEGER,
	PRIMARY KEY (id),
	UNIQUE (task_id)
);

CREATE INDEX ix_chatbi_message_conversation_sequence ON chatbi_messages (conversation_id, sequence);

CREATE INDEX ix_chatbi_messages_conversation_id ON chatbi_messages (conversation_id);

CREATE INDEX ix_chatbi_messages_owner ON chatbi_messages (owner);

CREATE TABLE IF NOT EXISTS chatbi_ppt_model_config (
	id INTEGER NOT NULL AUTO_INCREMENT,
	provider_id INTEGER NOT NULL,
	model VARCHAR(200) NOT NULL,
	updated_by INTEGER,
	updated_at INTEGER NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS chatbi_results (
	id VARCHAR(36) NOT NULL,
	conversation_id VARCHAR(36) NOT NULL,
	message_id VARCHAR(36) NOT NULL,
	owner VARCHAR(64) NOT NULL,
	title VARCHAR(512) NOT NULL,
	columns JSON NOT NULL,
	`rows` JSON NOT NULL,
	total_rows INTEGER NOT NULL,
	complete BOOL NOT NULL,
	created_at INTEGER NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_chatbi_results_conversation_id ON chatbi_results (conversation_id);

CREATE INDEX ix_chatbi_results_message_id ON chatbi_results (message_id);

CREATE INDEX ix_chatbi_results_owner ON chatbi_results (owner);

CREATE TABLE IF NOT EXISTS chatbi_trace_lookup (
	trace_id VARCHAR(36) NOT NULL,
	message_id VARCHAR(36) NOT NULL,
	PRIMARY KEY (trace_id, message_id)
);

CREATE INDEX ix_chatbi_trace_lookup_message_id ON chatbi_trace_lookup (message_id);

CREATE TABLE IF NOT EXISTS data_source (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(100) NOT NULL,
	database_type VARCHAR(50) NOT NULL,
	host VARCHAR(255) NOT NULL,
	port INTEGER NOT NULL,
	username VARCHAR(100) NOT NULL,
	password VARCHAR(500) NOT NULL,
	default_database VARCHAR(100) NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_data_source_id ON data_source (id);

CREATE INDEX ix_data_source_space_id ON data_source (space_id);

CREATE TABLE IF NOT EXISTS data_sync_tasks (
	id VARCHAR(16) NOT NULL,
	name VARCHAR(100) NOT NULL,
	schedule_enabled BOOL NOT NULL,
	cron_expression VARCHAR(100) NOT NULL,
	timezone VARCHAR(64) NOT NULL,
	next_run_at BIGINT,
	active_run_id VARCHAR(36),
	last_run_id VARCHAR(36),
	created_at BIGINT NOT NULL,
	updated_at BIGINT NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_data_sync_tasks_next_run_at ON data_sync_tasks (next_run_at);

CREATE TABLE IF NOT EXISTS embedding_configs (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(100) NOT NULL COMMENT '配置名称',
	provider VARCHAR(50) NOT NULL COMMENT '提供商',
	api_key VARCHAR(500) COMMENT 'API Key',
	model VARCHAR(100) NOT NULL COMMENT '模型名称',
	dimension INTEGER NOT NULL COMMENT '向量维度',
	base_url VARCHAR(255) COMMENT 'API Base URL',
	is_default BOOL NOT NULL COMMENT '是否默认启用',
	is_active BOOL NOT NULL COMMENT '是否启用',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	updated_at DATETIME COMMENT '更新时间' DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uq_embedding_config_default_flag_per_space UNIQUE (is_default, space_id)
);

CREATE INDEX ix_embedding_configs_id ON embedding_configs (id);

CREATE INDEX ix_embedding_configs_space_id ON embedding_configs (space_id);

CREATE TABLE IF NOT EXISTS es_configs (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(100) NOT NULL COMMENT '配置名称',
	host VARCHAR(255) COMMENT 'ES Host地址',
	port VARCHAR(20) COMMENT '端口',
	username VARCHAR(100) COMMENT '用户名',
	password VARCHAR(500) COMMENT '密码',
	is_default BOOL NOT NULL COMMENT '是否默认启用',
	is_active BOOL NOT NULL COMMENT '是否启用',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	updated_at DATETIME COMMENT '更新时间' DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uq_es_config_default_flag_per_space UNIQUE (is_default, space_id)
);

CREATE INDEX ix_es_configs_id ON es_configs (id);

CREATE INDEX ix_es_configs_space_id ON es_configs (space_id);

CREATE TABLE IF NOT EXISTS eval_case_ground_truths (
	id INTEGER NOT NULL AUTO_INCREMENT,
	case_id INTEGER NOT NULL COMMENT '所属用例ID',
	version VARCHAR(50) COMMENT '参考答案版本',
	ground_truth TEXT NOT NULL COMMENT '参考答案内容',
	ground_truth_type VARCHAR(20) COMMENT '参考答案格式',
	comparison_method VARCHAR(30) NOT NULL COMMENT '对比方式',
	comparison_config JSON COMMENT '对比配置参数',
	is_active BOOL COMMENT '是否启用',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_case_ground_truths_case_id ON eval_case_ground_truths (case_id);

CREATE INDEX ix_eval_case_ground_truths_id ON eval_case_ground_truths (id);

CREATE TABLE IF NOT EXISTS eval_cases (
	id INTEGER NOT NULL AUTO_INCREMENT,
	suite_id INTEGER NOT NULL COMMENT '所属评测集ID',
	input_prompt TEXT NOT NULL COMMENT '输入提示词',
	input_variables JSON COMMENT '模板变量值',
	expected_output_type VARCHAR(20) COMMENT '期望输出类型',
	difficulty VARCHAR(20) COMMENT '难度：easy/medium/hard',
	category VARCHAR(100) COMMENT '问题分类',
	remark TEXT COMMENT '备注',
	sort_order INTEGER COMMENT '排序序号',
	is_active BOOL COMMENT '是否启用',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_cases_id ON eval_cases (id);

CREATE INDEX ix_eval_cases_suite_id ON eval_cases (suite_id);

CREATE TABLE IF NOT EXISTS eval_comparison_templates (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(100) NOT NULL COMMENT '模板名称',
	description VARCHAR(500) COMMENT '模板描述',
	system_prompt TEXT NOT NULL COMMENT '系统提示词',
	user_prompt TEXT NOT NULL COMMENT '用户提示词模板，包含 {question} {expected} {generated_sql} 占位符',
	comparison_method VARCHAR(30) COMMENT '对比方式',
	is_default BOOL COMMENT '是否默认模板',
	is_system BOOL COMMENT '系统内置模板，不可删除/编辑',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_comparison_templates_id ON eval_comparison_templates (id);

CREATE INDEX ix_eval_comparison_templates_space_id ON eval_comparison_templates (space_id);

CREATE TABLE IF NOT EXISTS eval_comparisons (
	id INTEGER NOT NULL AUTO_INCREMENT,
	run_id INTEGER NOT NULL COMMENT '所属运行记录ID',
	ground_truth_id INTEGER NOT NULL COMMENT '使用的参考答案ID',
	comparison_method VARCHAR(30) NOT NULL COMMENT '对比方式',
	is_correct BOOL COMMENT '是否通过',
	score NUMERIC(5, 4) COMMENT '得分 0-1',
	comparison_detail JSON COMMENT '对比详情',
	llm_judge_raw_output TEXT COMMENT 'LLM评判原始输出',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_comparisons_id ON eval_comparisons (id);

CREATE INDEX ix_eval_comparisons_run_id ON eval_comparisons (run_id);

CREATE TABLE IF NOT EXISTS eval_configs (
	id INTEGER NOT NULL AUTO_INCREMENT,
	`key` VARCHAR(100) NOT NULL COMMENT '配置键',
	value VARCHAR(500) NOT NULL COMMENT '配置值',
	description VARCHAR(500) COMMENT '配置说明',
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	UNIQUE (`key`)
);

CREATE INDEX ix_eval_configs_id ON eval_configs (id);

CREATE TABLE IF NOT EXISTS eval_folders (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	parent_id INTEGER COMMENT '父文件夹ID',
	name VARCHAR(100) NOT NULL COMMENT '文件夹名称',
	description TEXT COMMENT '文件夹描述',
	sort_order INTEGER COMMENT '排序序号',
	is_system BOOL COMMENT '系统文件夹',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_folders_id ON eval_folders (id);

CREATE INDEX ix_eval_folders_parent_id ON eval_folders (parent_id);

CREATE INDEX ix_eval_folders_space_id ON eval_folders (space_id);

CREATE TABLE IF NOT EXISTS eval_output_templates (
	id INTEGER NOT NULL AUTO_INCREMENT,
	suite_id INTEGER NOT NULL COMMENT '所属评测集ID',
	name VARCHAR(100) NOT NULL COMMENT '模板名称',
	fields JSON NOT NULL COMMENT '字段定义列表',
	is_default BOOL COMMENT '是否默认模板',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_output_templates_id ON eval_output_templates (id);

CREATE INDEX ix_eval_output_templates_suite_id ON eval_output_templates (suite_id);

CREATE TABLE IF NOT EXISTS eval_runs (
	id INTEGER NOT NULL AUTO_INCREMENT,
	sub_task_id INTEGER NOT NULL COMMENT '所属子任务ID',
	case_id INTEGER NOT NULL COMMENT '评测用例ID',
	status VARCHAR(20) COMMENT '状态',
	raw_response TEXT COMMENT '原始响应',
	parsed_response JSON COMMENT '解析后的响应',
	error_message TEXT COMMENT '错误信息',
	execution_time_ms INTEGER COMMENT '执行耗时ms',
	attempt INTEGER COMMENT '尝试次数',
	started_at TIMESTAMP NULL COMMENT '开始时间',
	completed_at TIMESTAMP NULL COMMENT '完成时间',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_runs_case_id ON eval_runs (case_id);

CREATE INDEX ix_eval_runs_id ON eval_runs (id);

CREATE INDEX ix_eval_runs_sub_task_id ON eval_runs (sub_task_id);

CREATE TABLE IF NOT EXISTS eval_schedules (
	id INTEGER NOT NULL AUTO_INCREMENT,
	suite_id INTEGER NOT NULL COMMENT '关联评测集ID',
	name VARCHAR(200) NOT NULL COMMENT '定时任务名称',
	task_config JSON COMMENT '创建任务时的参数',
	cron_expression VARCHAR(50) NOT NULL COMMENT 'Cron表达式',
	is_active BOOL COMMENT '是否启用',
	last_run_at TIMESTAMP NULL COMMENT '上次执行时间',
	last_task_id INTEGER COMMENT '上次创建的任务ID',
	next_run_at TIMESTAMP NULL COMMENT '下次执行时间',
	notify_on_failure BOOL COMMENT '失败时通知',
	notify_channels JSON COMMENT '通知渠道配置',
	created_by INTEGER NOT NULL COMMENT '创建者ID',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_schedules_id ON eval_schedules (id);

CREATE INDEX ix_eval_schedules_suite_id ON eval_schedules (suite_id);

CREATE TABLE IF NOT EXISTS eval_sub_tasks (
	id INTEGER NOT NULL AUTO_INCREMENT,
	task_id INTEGER NOT NULL COMMENT '所属任务ID',
	target_type VARCHAR(30) NOT NULL COMMENT '评测对象类型',
	target_id INTEGER COMMENT '评测对象ID',
	target_config JSON COMMENT '评测对象配置',
	status VARCHAR(30) COMMENT '状态',
	total_cases INTEGER COMMENT '总用例数',
	completed_cases INTEGER COMMENT '已完成数',
	passed_cases INTEGER COMMENT '通过数',
	failed_cases INTEGER COMMENT '未通过数',
	error_cases INTEGER COMMENT '错误数',
	started_at TIMESTAMP NULL COMMENT '开始时间',
	completed_at TIMESTAMP NULL COMMENT '完成时间',
	error_message TEXT COMMENT '错误信息',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_sub_tasks_id ON eval_sub_tasks (id);

CREATE INDEX ix_eval_sub_tasks_task_id ON eval_sub_tasks (task_id);

CREATE TABLE IF NOT EXISTS eval_suites (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	folder_id INTEGER NOT NULL COMMENT '所属文件夹ID',
	name VARCHAR(200) NOT NULL COMMENT '评测集名称',
	description TEXT COMMENT '评测集描述',
	version VARCHAR(50) COMMENT '版本号',
	default_task_source_type VARCHAR(30) COMMENT '默认任务源类型',
	default_task_source_id INTEGER COMMENT '默认任务源ID',
	default_task_source_config JSON COMMENT '默认任务源配置',
	default_comparison_method VARCHAR(30) COMMENT '默认对比方式',
	default_comparison_config JSON COMMENT '默认对比配置',
	status VARCHAR(20) COMMENT '状态：draft/active/archived',
	share_token VARCHAR(64) COMMENT '外链分享token',
	created_by INTEGER NOT NULL COMMENT '创建者ID',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_suites_folder_id ON eval_suites (folder_id);

CREATE INDEX ix_eval_suites_id ON eval_suites (id);

CREATE UNIQUE INDEX ix_eval_suites_share_token ON eval_suites (share_token);

CREATE INDEX ix_eval_suites_space_id ON eval_suites (space_id);

CREATE TABLE IF NOT EXISTS eval_tags (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(50) NOT NULL COMMENT '标签名称',
	color VARCHAR(20) COMMENT '标签颜色',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_tags_id ON eval_tags (id);

CREATE INDEX ix_eval_tags_space_id ON eval_tags (space_id);

CREATE TABLE IF NOT EXISTS eval_tasks (
	id INTEGER NOT NULL AUTO_INCREMENT,
	suite_id INTEGER NOT NULL COMMENT '所属评测集ID',
	name VARCHAR(200) NOT NULL COMMENT '任务名称',
	description TEXT COMMENT '任务描述',
	output_template_id INTEGER COMMENT '输出模板ID',
	case_filter JSON COMMENT '用例过滤条件',
	exec_params JSON COMMENT '执行参数',
	status VARCHAR(30) COMMENT '状态',
	total_cases INTEGER COMMENT '总用例数',
	completed_cases INTEGER COMMENT '已完成数',
	passed_cases INTEGER COMMENT '通过数',
	failed_cases INTEGER COMMENT '未通过数',
	error_cases INTEGER COMMENT '错误数',
	scheduled_at TIMESTAMP NULL COMMENT '定时执行时间',
	started_at TIMESTAMP NULL COMMENT '开始时间',
	completed_at TIMESTAMP NULL COMMENT '完成时间',
	created_by INTEGER NOT NULL COMMENT '创建者ID',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_eval_tasks_id ON eval_tasks (id);

CREATE INDEX ix_eval_tasks_suite_id ON eval_tasks (suite_id);

CREATE TABLE IF NOT EXISTS invite_code (
	id INTEGER NOT NULL AUTO_INCREMENT,
	code VARCHAR(30) NOT NULL COMMENT '邀请码，最多30个字符',
	expires_at DATETIME NOT NULL COMMENT '邀请码过期时间',
	is_active BOOL COMMENT '是否启用',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL,
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_invite_code_code ON invite_code (code);

CREATE INDEX ix_invite_code_id ON invite_code (id);

CREATE TABLE IF NOT EXISTS kb_vector_manifest (
	id INTEGER NOT NULL AUTO_INCREMENT,
	kb_id INTEGER NOT NULL,
	domain VARCHAR(50) NOT NULL,
	table_name VARCHAR(255),
	field_code VARCHAR(500),
	item_key VARCHAR(512) NOT NULL,
	embedding_hash VARCHAR(64),
	payload_hash VARCHAR(64),
	item_value TEXT,
	last_seen_run_id VARCHAR(64) NOT NULL,
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uq_kb_vector_manifest_item UNIQUE (kb_id, domain, item_key)
);

CREATE INDEX ix_kb_vector_manifest_domain ON kb_vector_manifest (domain);

CREATE INDEX ix_kb_vector_manifest_field_code ON kb_vector_manifest (field_code);

CREATE INDEX ix_kb_vector_manifest_id ON kb_vector_manifest (id);

CREATE INDEX ix_kb_vector_manifest_kb_id ON kb_vector_manifest (kb_id);

CREATE INDEX ix_kb_vector_manifest_last_seen_run_id ON kb_vector_manifest (last_seen_run_id);

CREATE INDEX ix_kb_vector_manifest_table_name ON kb_vector_manifest (table_name);

CREATE TABLE IF NOT EXISTS model_providers (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT,
	name VARCHAR(100) NOT NULL COMMENT '供应商名称',
	base_url VARCHAR(500) NOT NULL COMMENT 'API Base URL',
	api_key VARCHAR(500) COMMENT 'API Key',
	protocol VARCHAR(50) COMMENT '协议类型: openai, anthropic, google等',
	models TEXT COMMENT '模型列表，JSON格式存储',
	model_settings JSON COMMENT '按模型名称保存思考配置',
	description TEXT COMMENT '备注说明',
	is_active BOOL COMMENT '是否启用',
	is_builtin BOOL COMMENT '是否为内置供应商',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	updated_at DATETIME COMMENT '更新时间' DEFAULT now(),
	PRIMARY KEY (id)
);

CREATE INDEX ix_model_providers_id ON model_providers (id);

CREATE TABLE IF NOT EXISTS oss_configs (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(100) NOT NULL COMMENT '配置名称',
	provider VARCHAR(50) NOT NULL COMMENT '存储提供商: aliyun/s3/azure/minio',
	endpoint VARCHAR(500) COMMENT ' Endpoint / Region',
	bucket VARCHAR(200) COMMENT 'Bucket 名称',
	access_key VARCHAR(200) COMMENT 'Access Key / Account Name',
	secret_key VARCHAR(500) COMMENT 'Secret Key / Account Key',
	prefix VARCHAR(200) COMMENT '存储路径前缀',
	region VARCHAR(100) COMMENT '区域/Region (S3/Azure)',
	extra_config TEXT COMMENT '扩展配置JSON',
	is_default BOOL NOT NULL COMMENT '是否默认启用',
	is_active BOOL NOT NULL COMMENT '是否启用',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	updated_at DATETIME COMMENT '更新时间' DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uq_oss_default_flag_per_space UNIQUE (is_default, space_id)
);

CREATE INDEX ix_oss_configs_id ON oss_configs (id);

CREATE INDEX ix_oss_configs_space_id ON oss_configs (space_id);

CREATE TABLE IF NOT EXISTS spaces (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(100) NOT NULL COMMENT '空间名称',
	code VARCHAR(50) NOT NULL COMMENT '空间编码',
	description TEXT COMMENT '空间描述',
	avatar VARCHAR(500) COMMENT '空间头像/图标URL',
	is_active BOOL COMMENT '是否启用',
	settings JSON COMMENT '空间个性化设置',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	UNIQUE (code)
);

CREATE INDEX ix_spaces_id ON spaces (id);

CREATE TABLE IF NOT EXISTS system_logs (
	id INTEGER NOT NULL AUTO_INCREMENT,
	created_at BIGINT NOT NULL,
	level VARCHAR(16) NOT NULL,
	service VARCHAR(64) NOT NULL,
	instance VARCHAR(128) NOT NULL,
	logger VARCHAR(255) NOT NULL,
	message TEXT NOT NULL,
	exception TEXT,
	request_id VARCHAR(64),
	conversation_id VARCHAR(36),
	message_id VARCHAR(36),
	trace_id VARCHAR(128),
	user_id VARCHAR(320),
	data JSON NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_system_logs_conversation_id ON system_logs (conversation_id);

CREATE INDEX ix_system_logs_created_at ON system_logs (created_at);

CREATE INDEX ix_system_logs_level ON system_logs (level);

CREATE INDEX ix_system_logs_level_time ON system_logs (level, created_at);

CREATE INDEX ix_system_logs_message_id ON system_logs (message_id);

CREATE INDEX ix_system_logs_request_id ON system_logs (request_id);

CREATE INDEX ix_system_logs_trace_id ON system_logs (trace_id);

CREATE INDEX ix_system_logs_user_id ON system_logs (user_id);

CREATE TABLE IF NOT EXISTS system_updates (
	id INTEGER NOT NULL AUTO_INCREMENT,
	version VARCHAR(20) NOT NULL COMMENT '版本号，如 v1.2.0',
	title VARCHAR(200) NOT NULL COMMENT '更新标题',
	content TEXT NOT NULL COMMENT '更新内容，支持HTML格式',
	update_type VARCHAR(20) NOT NULL COMMENT '更新类型: feature/improvement/fix/security',
	is_published BOOL COMMENT '是否已发布',
	release_date TIMESTAMP NOT NULL COMMENT '发布日期',
	created_at TIMESTAMP NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX idx_system_updates_is_published ON system_updates (is_published);

CREATE INDEX idx_system_updates_release_date ON system_updates (release_date);

CREATE INDEX idx_system_updates_version ON system_updates (version);

CREATE INDEX ix_system_updates_id ON system_updates (id);

CREATE TABLE IF NOT EXISTS user_space_last_access (
	user_id BIGINT NOT NULL COMMENT '用户ID' AUTO_INCREMENT,
	last_space_id INTEGER NOT NULL COMMENT '最后访问的空间ID',
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (user_id)
);

CREATE INDEX ix_user_space_last_access_user_id ON user_space_last_access (user_id);

CREATE TABLE IF NOT EXISTS user_space_roles (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	space_id INTEGER NOT NULL COMMENT '空间ID',
	`role` VARCHAR(20) NOT NULL COMMENT '角色：owner/admin/member/viewer',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	CONSTRAINT uk_user_space UNIQUE (user_id, space_id)
);

CREATE INDEX ix_user_space_roles_id ON user_space_roles (id);

CREATE INDEX ix_user_space_roles_space_id ON user_space_roles (space_id);

CREATE INDEX ix_user_space_roles_user_id ON user_space_roles (user_id);

CREATE TABLE IF NOT EXISTS users (
	id INTEGER NOT NULL AUTO_INCREMENT,
	username VARCHAR(64) NOT NULL COMMENT '用户名',
	display_name VARCHAR(128) COMMENT '显示名称',
	password_hash VARCHAR(256) COMMENT '密码哈希',
	system_role VARCHAR(20) NOT NULL COMMENT '系统级角色',
	is_active BOOL NOT NULL COMMENT '是否启用',
	is_preset_admin BOOL NOT NULL COMMENT '是否预设管理员',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE INDEX ix_users_id ON users (id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE IF NOT EXISTS vector_store_configs (
	id INTEGER NOT NULL COMMENT '主键ID' AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(100) NOT NULL COMMENT '向量库名称',
	provider VARCHAR(50) NOT NULL COMMENT '向量库类型',
	host VARCHAR(255) COMMENT '地址/Host',
	port VARCHAR(20) COMMENT '端口',
	username VARCHAR(100) COMMENT '用户名',
	password VARCHAR(500) COMMENT '密码',
	`database` VARCHAR(100) COMMENT '数据库/namespace',
	collection_prefix VARCHAR(100) COMMENT '集合前缀',
	dimension INTEGER COMMENT '向量维度',
	extra_config TEXT COMMENT '扩展配置JSON',
	is_active BOOL NOT NULL COMMENT '是否启用',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	updated_at DATETIME COMMENT '更新时间' DEFAULT now(),
	PRIMARY KEY (id)
);

CREATE INDEX ix_vector_store_configs_id ON vector_store_configs (id);

CREATE INDEX ix_vector_store_configs_space_id ON vector_store_configs (space_id);

CREATE TABLE IF NOT EXISTS xlsx_qa_module (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(128) NOT NULL,
	description VARCHAR(500),
	owner_display_name VARCHAR(128),
	llm_provider_id INTEGER,
	llm_model VARCHAR(128),
	extra_config_json JSON,
	share_token VARCHAR(64),
	module_understanding_md TEXT,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_xlsx_qa_module_id ON xlsx_qa_module (id);

CREATE UNIQUE INDEX ix_xlsx_qa_module_share_token ON xlsx_qa_module (share_token);

CREATE INDEX ix_xlsx_qa_module_space_id ON xlsx_qa_module (space_id);

CREATE TABLE IF NOT EXISTS xlsx_qa_ppt_template (
	id VARCHAR(32) NOT NULL,
	name VARCHAR(100) NOT NULL,
	description VARCHAR(200) NOT NULL,
	layout VARCHAR(32) NOT NULL COMMENT '布局类型: sidebar/header/minimal/dark_full/diagonal/corner/right_panel/dark_header',
	colors JSON NOT NULL COMMENT '颜色配置 JSON',
	layout_config JSON COMMENT '布局参数覆盖 JSON',
	is_builtin BOOL NOT NULL,
	sort_order INTEGER NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS agent_app (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	folder_id INTEGER NOT NULL,
	name VARCHAR(128) NOT NULL,
	icon VARCHAR(32) NOT NULL,
	description VARCHAR(500),
	owner_display_name VARCHAR(128),
	api_token VARCHAR(128) COMMENT '对外调用 token，由 bootcamp 侧维护',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL,
	PRIMARY KEY (id),
	FOREIGN KEY(folder_id) REFERENCES agent_app_folders (id) ON DELETE RESTRICT
);

CREATE INDEX ix_agent_app_folder_id ON agent_app (folder_id);

CREATE INDEX ix_agent_app_id ON agent_app (id);

CREATE INDEX ix_agent_app_space_id ON agent_app (space_id);

CREATE TABLE IF NOT EXISTS data_sync_runs (
	id VARCHAR(36) NOT NULL,
	task_id VARCHAR(16) NOT NULL,
	task_name VARCHAR(100) NOT NULL,
	trigger_type VARCHAR(16) NOT NULL,
	requested_by INTEGER,
	status VARCHAR(20) NOT NULL,
	stage VARCHAR(20) NOT NULL,
	page_no INTEGER NOT NULL,
	fetched_rows BIGINT NOT NULL,
	loaded_rows BIGINT NOT NULL,
	total_rows BIGINT,
	message TEXT,
	error TEXT,
	worker_id VARCHAR(36),
	lease_until BIGINT,
	created_at BIGINT NOT NULL,
	started_at BIGINT,
	finished_at BIGINT,
	PRIMARY KEY (id),
	FOREIGN KEY(task_id) REFERENCES data_sync_tasks (id)
);

CREATE INDEX ix_data_sync_runs_created_at ON data_sync_runs (created_at);

CREATE INDEX ix_data_sync_runs_lease_until ON data_sync_runs (lease_until);

CREATE INDEX ix_data_sync_runs_status ON data_sync_runs (status);

CREATE INDEX ix_data_sync_runs_task_id ON data_sync_runs (task_id);

CREATE TABLE IF NOT EXISTS eval_suite_tags (
	suite_id INTEGER NOT NULL,
	tag_id INTEGER NOT NULL,
	PRIMARY KEY (suite_id, tag_id),
	FOREIGN KEY(suite_id) REFERENCES eval_suites (id) ON DELETE CASCADE,
	FOREIGN KEY(tag_id) REFERENCES eval_tags (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_access (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(255) NOT NULL,
	description TEXT,
	data_source_id INTEGER NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL,
	PRIMARY KEY (id),
	FOREIGN KEY(data_source_id) REFERENCES data_source (id)
);

CREATE INDEX ix_knowledge_access_id ON knowledge_access (id);

CREATE INDEX ix_knowledge_access_space_id ON knowledge_access (space_id);

CREATE TABLE IF NOT EXISTS xlsx_qa_conversation (
	id INTEGER NOT NULL AUTO_INCREMENT,
	module_id INTEGER NOT NULL,
	title VARCHAR(255) NOT NULL,
	active_sheet_ids JSON,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(module_id) REFERENCES xlsx_qa_module (id) ON DELETE CASCADE
);

CREATE INDEX ix_xlsx_qa_conversation_id ON xlsx_qa_conversation (id);

CREATE INDEX ix_xlsx_qa_conversation_module_id ON xlsx_qa_conversation (module_id);

CREATE TABLE IF NOT EXISTS xlsx_qa_document (
	id INTEGER NOT NULL AUTO_INCREMENT,
	module_id INTEGER NOT NULL,
	file_name VARCHAR(255) NOT NULL,
	file_size BIGINT NOT NULL,
	oss_object_key VARCHAR(512) NOT NULL,
	sheet_name VARCHAR(255),
	data_table_name VARCHAR(128),
	total_rows INTEGER NOT NULL,
	total_columns INTEGER NOT NULL,
	columns_json JSON,
	understanding_md TEXT,
	suggested_questions_json JSON,
	status VARCHAR(32) NOT NULL,
	parse_error TEXT,
	sheet_count INTEGER NOT NULL,
	is_primary BOOL NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(module_id) REFERENCES xlsx_qa_module (id) ON DELETE CASCADE
);

CREATE INDEX ix_xlsx_qa_document_id ON xlsx_qa_document (id);

CREATE INDEX ix_xlsx_qa_document_module_id ON xlsx_qa_document (module_id);

CREATE TABLE IF NOT EXISTS xlsx_qa_insight_report (
	id INTEGER NOT NULL AUTO_INCREMENT,
	module_id INTEGER NOT NULL,
	status VARCHAR(32) NOT NULL,
	phase VARCHAR(32) NOT NULL,
	role_cards_json JSON,
	dimensions_json JSON,
	evidence_json JSON,
	dim_texts_json JSON,
	final_md TEXT,
	elapsed_ms INTEGER,
	error_message TEXT,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(module_id) REFERENCES xlsx_qa_module (id) ON DELETE CASCADE
);

CREATE INDEX ix_xlsx_qa_insight_report_id ON xlsx_qa_insight_report (id);

CREATE UNIQUE INDEX ix_xlsx_qa_insight_report_module_id ON xlsx_qa_insight_report (module_id);

CREATE TABLE IF NOT EXISTS agent_app_version (
	id INTEGER NOT NULL AUTO_INCREMENT,
	agent_app_id INTEGER NOT NULL,
	name VARCHAR(64) NOT NULL,
	status VARCHAR(32) NOT NULL,
	mode VARCHAR(64) NOT NULL,
	is_output BOOL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	workflow_json JSON,
	workflow_rev INTEGER NOT NULL DEFAULT '0',
	PRIMARY KEY (id),
	FOREIGN KEY(agent_app_id) REFERENCES agent_app (id) ON DELETE CASCADE
);

CREATE INDEX ix_agent_app_version_agent_app_id ON agent_app_version (agent_app_id);

CREATE INDEX ix_agent_app_version_id ON agent_app_version (id);

CREATE TABLE IF NOT EXISTS data_sync_events (
	id INTEGER NOT NULL AUTO_INCREMENT,
	run_id VARCHAR(36) NOT NULL,
	stage VARCHAR(20) NOT NULL,
	message TEXT NOT NULL,
	page_no INTEGER NOT NULL,
	fetched_rows BIGINT NOT NULL,
	loaded_rows BIGINT NOT NULL,
	created_at BIGINT NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(run_id) REFERENCES data_sync_runs (id)
);

CREATE INDEX ix_data_sync_events_run_id ON data_sync_events (run_id);

CREATE TABLE IF NOT EXISTS knowledge_base (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	name VARCHAR(255) NOT NULL,
	description TEXT,
	knowledge_access_id INTEGER NOT NULL,
	table_count INTEGER,
	vector_progress INTEGER,
	vectorization_status VARCHAR(20),
	vector_collection_name VARCHAR(100),
	vectorization_steps TEXT,
	current_vectorization_step VARCHAR(50),
	knowledge_term_dirty BOOL,
	sample_library_dirty BOOL,
	status BOOL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_access_id) REFERENCES knowledge_access (id)
);

CREATE INDEX ix_knowledge_base_id ON knowledge_base (id);

CREATE INDEX ix_knowledge_base_space_id ON knowledge_base (space_id);

CREATE TABLE IF NOT EXISTS knowledge_term (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	knowledge_access_id INTEGER NOT NULL,
	term_name VARCHAR(255) NOT NULL,
	term_value TEXT NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_access_id) REFERENCES knowledge_access (id)
);

CREATE INDEX ix_knowledge_term_id ON knowledge_term (id);

CREATE INDEX ix_knowledge_term_space_id ON knowledge_term (space_id);

CREATE TABLE IF NOT EXISTS sample_library (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	knowledge_access_id INTEGER NOT NULL,
	sample_name VARCHAR(255) NOT NULL,
	sql_content TEXT NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_access_id) REFERENCES knowledge_access (id)
);

CREATE INDEX ix_sample_library_id ON sample_library (id);

CREATE INDEX ix_sample_library_space_id ON sample_library (space_id);

CREATE TABLE IF NOT EXISTS table_structure (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	knowledge_access_id INTEGER NOT NULL,
	table_name VARCHAR(255) NOT NULL,
	table_alias VARCHAR(255),
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_access_id) REFERENCES knowledge_access (id)
);

CREATE INDEX ix_table_structure_id ON table_structure (id);

CREATE INDEX ix_table_structure_space_id ON table_structure (space_id);

CREATE TABLE IF NOT EXISTS xlsx_qa_message (
	id INTEGER NOT NULL AUTO_INCREMENT,
	conversation_id INTEGER NOT NULL,
	`role` VARCHAR(16) NOT NULL,
	content TEXT,
	status VARCHAR(32) NOT NULL,
	extras_json JSON,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES xlsx_qa_conversation (id) ON DELETE CASCADE
);

CREATE INDEX ix_xlsx_qa_message_conversation_id ON xlsx_qa_message (conversation_id);

CREATE INDEX ix_xlsx_qa_message_id ON xlsx_qa_message (id);

CREATE TABLE IF NOT EXISTS xlsx_qa_ppt_history (
	id INTEGER NOT NULL AUTO_INCREMENT,
	module_id INTEGER NOT NULL,
	conversation_id INTEGER NOT NULL,
	conversation_title VARCHAR(255) NOT NULL,
	template_id VARCHAR(32) NOT NULL,
	status VARCHAR(32) NOT NULL,
	status_message TEXT,
	progress_messages_json JSON,
	error_message TEXT,
	oss_object_key VARCHAR(512),
	file_size BIGINT,
	options_json JSON,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(module_id) REFERENCES xlsx_qa_module (id) ON DELETE CASCADE,
	FOREIGN KEY(conversation_id) REFERENCES xlsx_qa_conversation (id) ON DELETE CASCADE
);

CREATE INDEX ix_xlsx_qa_ppt_history_conversation_id ON xlsx_qa_ppt_history (conversation_id);

CREATE INDEX ix_xlsx_qa_ppt_history_id ON xlsx_qa_ppt_history (id);

CREATE INDEX ix_xlsx_qa_ppt_history_module_id ON xlsx_qa_ppt_history (module_id);

CREATE TABLE IF NOT EXISTS xlsx_qa_sheet (
	id INTEGER NOT NULL AUTO_INCREMENT,
	document_id INTEGER NOT NULL,
	sheet_index INTEGER NOT NULL COMMENT 'Sheet 序号（0-based，最多 5 个）',
	sheet_name VARCHAR(255) NOT NULL,
	data_table_name VARCHAR(128) NOT NULL,
	total_rows INTEGER NOT NULL,
	total_columns INTEGER NOT NULL,
	columns_json JSON,
	understanding_md TEXT,
	suggested_questions_json JSON,
	status VARCHAR(32) NOT NULL,
	parse_error TEXT,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(document_id) REFERENCES xlsx_qa_document (id) ON DELETE CASCADE,
	UNIQUE (data_table_name)
);

CREATE INDEX ix_xlsx_qa_sheet_document_id ON xlsx_qa_sheet (document_id);

CREATE INDEX ix_xlsx_qa_sheet_id ON xlsx_qa_sheet (id);

CREATE TABLE IF NOT EXISTS autobi_projects (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	api_access_id VARCHAR(10),
	share_token VARCHAR(64),
	name VARCHAR(255) NOT NULL,
	description TEXT,
	knowledge_base_id INTEGER,
	folder_id INTEGER NOT NULL DEFAULT '1',
	config_json LONGTEXT NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	is_deleted BOOL,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_base (id),
	FOREIGN KEY(folder_id) REFERENCES autobi_folders (id)
);

CREATE UNIQUE INDEX ix_autobi_projects_api_access_id ON autobi_projects (api_access_id);

CREATE INDEX ix_autobi_projects_id ON autobi_projects (id);

CREATE UNIQUE INDEX ix_autobi_projects_share_token ON autobi_projects (share_token);

CREATE INDEX ix_autobi_projects_space_id ON autobi_projects (space_id);

CREATE TABLE IF NOT EXISTS kb_knowledge_term (
	id INTEGER NOT NULL AUTO_INCREMENT,
	knowledge_base_id INTEGER NOT NULL,
	knowledge_term_id INTEGER NOT NULL,
	term_name_cache VARCHAR(255) COMMENT '词条名称缓存',
	term_value_cache TEXT COMMENT '词条值缓存',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_base (id),
	FOREIGN KEY(knowledge_term_id) REFERENCES knowledge_term (id)
);

CREATE INDEX ix_kb_knowledge_term_id ON kb_knowledge_term (id);

CREATE TABLE IF NOT EXISTS kb_ner_row (
	id INTEGER NOT NULL AUTO_INCREMENT,
	space_id INTEGER NOT NULL COMMENT '所属空间ID',
	knowledge_base_id INTEGER NOT NULL,
	sheet_name VARCHAR(64) NOT NULL,
	table_name VARCHAR(50) NOT NULL,
	field_name VARCHAR(50) NOT NULL,
	standard_name VARCHAR(50) NOT NULL,
	alias VARCHAR(50) NOT NULL,
	remark VARCHAR(50) NOT NULL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_base (id)
);

CREATE INDEX ix_kb_ner_row_id ON kb_ner_row (id);

CREATE INDEX ix_kb_ner_row_knowledge_base_id ON kb_ner_row (knowledge_base_id);

CREATE INDEX ix_kb_ner_row_space_id ON kb_ner_row (space_id);

CREATE TABLE IF NOT EXISTS kb_sample_library (
	id INTEGER NOT NULL AUTO_INCREMENT,
	knowledge_base_id INTEGER NOT NULL,
	sample_id INTEGER NOT NULL,
	sample_name_cache VARCHAR(255) COMMENT '样例名称缓存',
	sample_content_cache TEXT COMMENT '样例内容缓存',
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_base (id),
	FOREIGN KEY(sample_id) REFERENCES sample_library (id)
);

CREATE INDEX ix_kb_sample_library_id ON kb_sample_library (id);

CREATE TABLE IF NOT EXISTS kb_table_structure (
	id INTEGER NOT NULL AUTO_INCREMENT,
	knowledge_base_id INTEGER NOT NULL,
	table_structure_id INTEGER NOT NULL,
	table_name VARCHAR(255) NOT NULL,
	table_alias VARCHAR(255),
	is_vectorized BOOL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_base (id),
	FOREIGN KEY(table_structure_id) REFERENCES table_structure (id)
);

CREATE INDEX ix_kb_table_structure_id ON kb_table_structure (id);

CREATE TABLE IF NOT EXISTS table_field (
	id INTEGER NOT NULL AUTO_INCREMENT,
	table_structure_id INTEGER NOT NULL,
	field_name VARCHAR(255) NOT NULL,
	field_alias VARCHAR(255),
	field_type VARCHAR(50) NOT NULL,
	is_enabled BOOL,
	is_vectorized BOOL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(table_structure_id) REFERENCES table_structure (id)
);

CREATE INDEX ix_table_field_id ON table_field (id);

CREATE TABLE IF NOT EXISTS autobi_lab_chat_state (
	project_id INTEGER NOT NULL,
	payload_json LONGTEXT NOT NULL,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (project_id),
	FOREIGN KEY(project_id) REFERENCES autobi_projects (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS kb_table_field (
	id INTEGER NOT NULL AUTO_INCREMENT,
	kb_table_structure_id INTEGER NOT NULL,
	table_field_id INTEGER NOT NULL,
	field_name VARCHAR(255) NOT NULL,
	field_alias VARCHAR(255),
	field_type VARCHAR(50) NOT NULL,
	is_vectorized BOOL,
	is_enabled BOOL,
	is_value_vectorized BOOL,
	created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(kb_table_structure_id) REFERENCES kb_table_structure (id),
	FOREIGN KEY(table_field_id) REFERENCES table_field (id)
);

CREATE INDEX ix_kb_table_field_id ON kb_table_field (id);

SET FOREIGN_KEY_CHECKS=1;
