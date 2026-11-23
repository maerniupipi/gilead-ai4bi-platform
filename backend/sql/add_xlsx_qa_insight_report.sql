-- 已有环境升级：创建洞察报告表（与 init_tables.sql 中 18c 段一致）
-- 用法示例：mysql -h ... -u ... -p app_uat < backend/sql/add_xlsx_qa_insight_report.sql

CREATE TABLE IF NOT EXISTS `xlsx_qa_insight_report` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `module_id` INT NOT NULL COMMENT '每模块最多一条（unique）',
  `status` VARCHAR(32) NOT NULL DEFAULT 'generating' COMMENT 'generating|done|failed',
  `phase` VARCHAR(32) NOT NULL DEFAULT 'profile' COMMENT '当前流水线阶段',
  `role_cards_json` JSON NULL COMMENT '角色卡状态',
  `dimensions_json` JSON NULL COMMENT '维度规划与问题',
  `evidence_json` JSON NULL COMMENT '按维度的 SQL 证据与样本',
  `dim_texts_json` JSON NULL COMMENT '各维度 Markdown',
  `final_md` MEDIUMTEXT NULL COMMENT '洞察总结 Markdown',
  `elapsed_ms` INT NULL,
  `error_message` TEXT NULL,
  `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_xlsx_qa_insight_report_module` (`module_id`),
  CONSTRAINT `fk_xlsx_qa_insight_report_module` FOREIGN KEY (`module_id`)
    REFERENCES `xlsx_qa_module` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
