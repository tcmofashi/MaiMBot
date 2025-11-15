"""
MaiBot 代码迁移工具
提供代码自动迁移、API兼容性检查和批量重构功能

作者: Claude
创建时间: 2025-01-12
"""

import re
import json
from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

from src.common.logger import get_logger

logger = get_logger("code_migration_tools")


class MigrationType(Enum):
    """迁移类型枚举"""

    ISOLATION_CONTEXT = "isolation_context"  # IsolationContext抽象层迁移
    CONFIG_SYSTEM = "config_system"  # 配置系统迁移
    CHAT_STREAM = "chat_stream"  # ChatStream系统迁移
    DATABASE_ACCESS = "database_access"  # 数据库访问迁移
    API_COMPATIBILITY = "api_compatibility"  # API兼容性迁移


class ChangeType(Enum):
    """变更类型枚举"""

    IMPORT_ADD = "import_add"
    IMPORT_REMOVE = "import_remove"
    FUNCTION_CALL_UPDATE = "function_call_update"
    CLASS_USAGE_UPDATE = "class_usage_update"
    PARAMETER_ADD = "parameter_add"
    PARAMETER_REMOVE = "parameter_remove"
    CODE_INSERT = "code_insert"
    CODE_REPLACE = "code_replace"


@dataclass
class CodeChange:
    """代码变更定义"""

    file_path: str
    line_number: int
    change_type: ChangeType
    original_code: str
    new_code: str
    description: str
    migration_type: MigrationType
    confidence: float = 1.0


@dataclass
class MigrationRule:
    """迁移规则定义"""

    name: str
    migration_type: MigrationType
    pattern: str
    replacement: str
    description: str
    file_patterns: List[str]
    confidence: float = 1.0
    auto_apply: bool = True


@dataclass
class FileAnalysis:
    """文件分析结果"""

    file_path: str
    total_lines: int
    changes_required: List[CodeChange]
    complexity_score: float
    risk_level: str  # low, medium, high, critical
    dependencies: List[str]


class CodeMigrationTools:
    """代码迁移工具集"""

    def __init__(self):
        self.project_root = Path("/home/tcmofashi/proj/MaiMBot")
        self.src_dir = self.project_root / "src"
        self.changes: List[CodeChange] = []
        self.migration_rules = self._initialize_migration_rules()
        self.backup_enabled = True
        self.dry_run = False

        # 迁移配置
        self.migration_config = {
            "max_file_size_mb": 10,
            "backup_directory": "/tmp/maibot_code_migration_backup",
            "skip_patterns": ["__pycache__", ".git", "*.pyc", "node_modules", ".pytest_cache"],
            "high_risk_patterns": ["database.py", "config.py", "main.py", "bot.py"],
        }

    def _initialize_migration_rules(self) -> List[MigrationRule]:
        """初始化迁移规则"""
        return [
            # IsolationContext 迁移规则
            MigrationRule(
                name="添加IsolationContext导入",
                migration_type=MigrationType.ISOLATION_CONTEXT,
                pattern=r"from (src\.)?isolation\.isolation_context import",
                replacement="from src.isolation.isolation_context import IsolationContext",
                description="添加IsolationContext导入语句",
                file_patterns=["*.py"],
                auto_apply=True,
            ),
            MigrationRule(
                name="函数参数添加IsolationContext",
                migration_type=MigrationType.ISOLATION_CONTEXT,
                pattern=r"def (\w+)\([^)]*):(?=\s*#.*?需要隔离上下文)",
                replacement=lambda m: f"def {m.group(1)}(isolation_context: IsolationContext, **kwargs):",
                description="为需要隔离的函数添加IsolationContext参数",
                file_patterns=["*.py"],
                auto_apply=False,
            ),
            # 配置系统迁移规则
            MigrationRule(
                name="配置访问迁移",
                migration_type=MigrationType.CONFIG_SYSTEM,
                pattern=r"get_config\(\)",
                replacement="get_config(isolation_context)",
                description="更新配置访问方法以支持隔离上下文",
                file_patterns=["*.py"],
                auto_apply=True,
            ),
            # ChatStream迁移规则
            MigrationRule(
                name="ChatStream创建迁移",
                migration_type=MigrationType.CHAT_STREAM,
                pattern=r"ChatStream\(",
                replacement="ChatStream(isolation_context=isolation_context, ",
                description="更新ChatStream创建以支持隔离上下文",
                file_patterns=["*.py"],
                auto_apply=False,
            ),
            # 数据库访问迁移规则
            MigrationRule(
                name="数据库查询迁移",
                migration_type=MigrationType.DATABASE_ACCESS,
                pattern=r"\.select\(\)\.where\(",
                replacement=".select().where(tenant_id=isolation_context.tenant_id, ",
                description="为数据库查询添加租户过滤",
                file_patterns=["*.py"],
                auto_apply=False,
            ),
            # API兼容性迁移规则
            MigrationRule(
                name="API函数参数更新",
                migration_type=MigrationType.API_COMPATIBILITY,
                pattern=r"def (\w+)\(self,([^)]*)\):",
                replacement=self._add_compatibility_parameters,
                description="为API函数添加向后兼容参数",
                file_patterns=["src/api/*.py"],
                auto_apply=False,
            ),
        ]

    def analyze_project(self) -> Dict[str, Any]:
        """分析整个项目，生成迁移报告"""
        logger.info("开始分析项目代码结构")

        analysis_result = {
            "total_files": 0,
            "files_requiring_migration": 0,
            "total_changes_required": 0,
            "migration_complexity": "low",
            "risk_assessment": {},
            "file_analyses": {},
            "migration_summary": {},
        }

        # 扫描Python文件
        python_files = list(self.src_dir.rglob("*.py"))
        analysis_result["total_files"] = len(python_files)

        high_risk_files = []
        medium_risk_files = []
        low_risk_files = []

        for file_path in python_files:
            if self._should_skip_file(file_path):
                continue

            try:
                file_analysis = self._analyze_file(file_path)
                analysis_result["file_analyses"][str(file_path)] = file_analysis

                if file_analysis.changes_required:
                    analysis_result["files_requiring_migration"] += 1
                    analysis_result["total_changes_required"] += len(file_analysis.changes_required)

                # 风险评估
                if file_analysis.risk_level == "critical":
                    high_risk_files.append(str(file_path))
                elif file_analysis.risk_level == "high":
                    high_risk_files.append(str(file_path))
                elif file_analysis.risk_level == "medium":
                    medium_risk_files.append(str(file_path))
                else:
                    low_risk_files.append(str(file_path))

            except Exception as e:
                logger.error(f"分析文件失败 {file_path}: {e}")

        # 风险评估
        analysis_result["risk_assessment"] = {
            "critical": len(high_risk_files),
            "high": len(
                [
                    f
                    for f in high_risk_files
                    if any(pattern in f for pattern in self.migration_config["high_risk_patterns"])
                ]
            ),
            "medium": len(medium_risk_files),
            "low": len(low_risk_files),
            "high_risk_files": high_risk_files,
            "medium_risk_files": medium_risk_files,
        }

        # 计算迁移复杂度
        if analysis_result["total_changes_required"] > 1000:
            analysis_result["migration_complexity"] = "high"
        elif analysis_result["total_changes_required"] > 500:
            analysis_result["migration_complexity"] = "medium"
        else:
            analysis_result["migration_complexity"] = "low"

        # 按迁移类型分组统计
        migration_by_type = {}
        for file_analysis in analysis_result["file_analyses"].values():
            for change in file_analysis.changes_required:
                migration_type = change.migration_type.value
                migration_by_type[migration_type] = migration_by_type.get(migration_type, 0) + 1

        analysis_result["migration_summary"] = migration_by_type

        logger.info(
            f"项目分析完成: {analysis_result['total_files']} 个文件，"
            f"{analysis_result['files_requiring_migration']} 个文件需要迁移，"
            f"共 {analysis_result['total_changes_required']} 处变更"
        )

        return analysis_result

    def _analyze_file(self, file_path: Path) -> FileAnalysis:
        """分析单个文件"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 基本统计信息
            total_lines = len(content.splitlines())

            # 检测需要的变更
            changes_required = self._detect_required_changes(file_path, content)

            # 计算复杂度分数
            complexity_score = self._calculate_complexity_score(content, changes_required)

            # 风险评估
            risk_level = self._assess_file_risk(file_path, content, changes_required)

            # 检测依赖
            dependencies = self._detect_dependencies(content)

            return FileAnalysis(
                file_path=str(file_path),
                total_lines=total_lines,
                changes_required=changes_required,
                complexity_score=complexity_score,
                risk_level=risk_level,
                dependencies=dependencies,
            )

        except Exception as e:
            logger.error(f"分析文件失败 {file_path}: {e}")
            return FileAnalysis(
                file_path=str(file_path),
                total_lines=0,
                changes_required=[],
                complexity_score=0.0,
                risk_level="low",
                dependencies=[],
            )

    def _detect_required_changes(self, file_path: Path, content: str) -> List[CodeChange]:
        """检测文件需要的变更"""
        changes = []

        for rule in self.migration_rules:
            if not self._matches_file_pattern(file_path, rule.file_patterns):
                continue

            try:
                # 应用规则检测变更
                matches = self._apply_rule(rule, content, file_path)
                changes.extend(matches)
            except Exception as e:
                logger.error(f"应用规则失败 {rule.name} 到 {file_path}: {e}")

        return changes

    def _apply_rule(self, rule: MigrationRule, content: str, file_path: Path) -> List[CodeChange]:
        """应用单个迁移规则"""
        changes = []
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            if re.search(rule.pattern, line):
                # 生成新的代码行
                if callable(rule.replacement):
                    new_line = rule.replacement(re.search(rule.pattern, line))
                else:
                    new_line = re.sub(rule.pattern, rule.replacement, line)

                if new_line != line:
                    change = CodeChange(
                        file_path=str(file_path),
                        line_number=line_num,
                        change_type=self._determine_change_type(rule),
                        original_code=line,
                        new_code=new_line,
                        description=rule.description,
                        migration_type=rule.migration_type,
                        confidence=rule.confidence,
                    )
                    changes.append(change)

        return changes

    def _determine_change_type(self, rule: MigrationRule) -> ChangeType:
        """确定变更类型"""
        if "import" in rule.pattern:
            return ChangeType.IMPORT_ADD
        elif "def" in rule.pattern:
            return ChangeType.FUNCTION_CALL_UPDATE
        elif "class" in rule.pattern:
            return ChangeType.CLASS_USAGE_UPDATE
        else:
            return ChangeType.CODE_REPLACE

    def _matches_file_pattern(self, file_path: Path, patterns: List[str]) -> bool:
        """检查文件是否匹配模式"""
        file_name = file_path.name
        file_str = str(file_path)

        for pattern in patterns:
            if pattern.startswith("*"):
                if file_name.endswith(pattern[1:]):
                    return True
            elif pattern in file_str:
                return True

        return False

    def _calculate_complexity_score(self, content: str, changes: List[CodeChange]) -> float:
        """计算复杂度分数"""
        base_score = len(content.splitlines()) / 1000  # 基于行数的基础分数
        change_score = len(changes) * 0.1  # 每个变更增加0.1分
        dependency_score = content.count("import ") * 0.05  # 每个导入增加0.05分

        return min(base_score + change_score + dependency_score, 10.0)

    def _assess_file_risk(self, file_path: Path, content: str, changes: List[CodeChange]) -> str:
        """评估文件风险等级"""
        # 高风险文件
        if any(pattern in str(file_path) for pattern in self.migration_config["high_risk_patterns"]):
            if len(changes) > 10:
                return "critical"
            return "high"

        # 基于变更数量评估
        if len(changes) > 20:
            return "high"
        elif len(changes) > 10:
            return "medium"
        elif len(changes) > 0:
            return "low"

        return "low"

    def _detect_dependencies(self, content: str) -> List[str]:
        """检测文件依赖"""
        dependencies = []
        import_patterns = [
            r"from (src\.[\w\.]+) import",
            r"import (src\.[\w\.]+)",
            r"from ([\w\.]+) import",
            r"import ([\w\.]+)",
        ]

        for pattern in import_patterns:
            matches = re.findall(pattern, content)
            dependencies.extend(matches)

        return list(set(dependencies))

    def _should_skip_file(self, file_path: Path) -> bool:
        """检查是否应该跳过文件"""
        file_str = str(file_path)

        # 检查跳过模式
        for pattern in self.migration_config["skip_patterns"]:
            if pattern in file_str:
                return True

        # 检查文件大小
        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self.migration_config["max_file_size_mb"]:
                logger.warning(f"文件过大，跳过: {file_path} ({file_size_mb:.2f}MB)")
                return True
        except OSError:
            return True

        return False

    def _add_compatibility_parameters(self, match):
        """添加兼容性参数的回调函数"""
        func_name = match.group(1)
        params = match.group(2).strip()

        if not params:
            return f"def {func_name}(self, isolation_context=None, **kwargs):"
        else:
            return f"def {func_name}(self, {params}, isolation_context=None, **kwargs):"

    def apply_migration(self, migration_types: List[MigrationType] = None, dry_run: bool = False) -> Dict[str, Any]:
        """应用代码迁移"""
        if migration_types is None:
            migration_types = list(MigrationType)

        self.dry_run = dry_run

        logger.info(f"开始应用代码迁移，类型: {[t.value for t in migration_types]}")

        result = {
            "total_files_processed": 0,
            "files_modified": 0,
            "total_changes_applied": 0,
            "failed_files": [],
            "skipped_files": [],
            "changes_by_type": {},
        }

        # 创建备份
        if self.backup_enabled and not dry_run:
            self._create_backup()

        # 分析项目
        analysis = self.analyze_project()

        # 按文件应用变更
        for file_path_str, file_analysis in analysis["file_analyses"].items():
            if not file_analysis.changes_required:
                continue

            file_path = Path(file_path_str)
            result["total_files_processed"] += 1

            try:
                # 过滤指定类型的变更
                applicable_changes = [
                    change for change in file_analysis.changes_required if change.migration_type in migration_types
                ]

                if not applicable_changes:
                    result["skipped_files"].append(file_path_str)
                    continue

                # 应用变更
                if self._apply_file_changes(file_path, applicable_changes):
                    result["files_modified"] += 1
                    result["total_changes_applied"] += len(applicable_changes)

                    # 统计变更类型
                    for change in applicable_changes:
                        change_type = change.migration_type.value
                        result["changes_by_type"][change_type] = result["changes_by_type"].get(change_type, 0) + 1
                else:
                    result["failed_files"].append(file_path_str)

            except Exception as e:
                logger.error(f"应用迁移失败 {file_path}: {e}")
                result["failed_files"].append(file_path_str)

        logger.info(
            f"代码迁移完成: 处理 {result['total_files_processed']} 个文件，"
            f"修改 {result['files_modified']} 个文件，"
            f"应用 {result['total_changes_applied']} 处变更"
        )

        return result

    def _apply_file_changes(self, file_path: Path, changes: List[CodeChange]) -> bool:
        """应用单个文件的变更"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # 按行号排序变更（从大到小，避免行号偏移）
            changes.sort(key=lambda x: x.line_number, reverse=True)

            # 应用变更
            for change in changes:
                line_index = change.line_number - 1
                if 0 <= line_index < len(lines):
                    if not self.dry_run:
                        lines[line_index] = change.new_code + "\n"
                    logger.debug(f"应用变更: {file_path}:{change.line_number} - {change.description}")

            # 写入文件
            if not self.dry_run:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

            return True

        except Exception as e:
            logger.error(f"应用文件变更失败 {file_path}: {e}")
            return False

    def _create_backup(self):
        """创建代码备份"""
        try:
            import shutil
            import datetime

            backup_dir = Path(self.migration_config["backup_directory"])
            backup_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"maibot_backup_{timestamp}"
            backup_path = backup_dir / backup_name

            logger.info(f"创建代码备份: {backup_path}")
            shutil.copytree(self.src_dir, backup_path)

        except Exception as e:
            logger.error(f"创建备份失败: {e}")

    def generate_migration_plan(self, output_file: str = "migration_plan.json") -> str:
        """生成迁移计划"""
        logger.info("生成代码迁移计划")

        analysis = self.analyze_project()

        migration_plan = {
            "metadata": {
                "generated_at": str(datetime.now()),
                "version": "1.0.0",
                "project_root": str(self.project_root),
            },
            "summary": {
                "total_files": analysis["total_files"],
                "files_requiring_migration": analysis["files_requiring_migration"],
                "total_changes_required": analysis["total_changes_required"],
                "migration_complexity": analysis["migration_complexity"],
            },
            "risk_assessment": analysis["risk_assessment"],
            "migration_phases": self._generate_migration_phases(analysis),
            "detailed_file_analysis": analysis["file_analyses"],
            "recommendations": self._generate_recommendations(analysis),
        }

        plan_file = self.project_root / output_file
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(migration_plan, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"迁移计划已生成: {plan_file}")
        return str(plan_file)

    def _generate_migration_phases(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成迁移阶段"""
        phases = [
            {
                "phase": 1,
                "name": "基础设施准备",
                "description": "创建IsolationContext抽象层和基础工具",
                "migration_types": ["isolation_context"],
                "estimated_files": self._count_files_by_type(analysis, "isolation_context"),
                "risk_level": "medium",
            },
            {
                "phase": 2,
                "name": "配置系统迁移",
                "description": "更新配置系统以支持多租户隔离",
                "migration_types": ["config_system"],
                "estimated_files": self._count_files_by_type(analysis, "config_system"),
                "risk_level": "high",
            },
            {
                "phase": 3,
                "name": "核心组件迁移",
                "description": "迁移ChatStream、数据库访问等核心组件",
                "migration_types": ["chat_stream", "database_access"],
                "estimated_files": (
                    self._count_files_by_type(analysis, "chat_stream")
                    + self._count_files_by_type(analysis, "database_access")
                ),
                "risk_level": "high",
            },
            {
                "phase": 4,
                "name": "API兼容性更新",
                "description": "更新API以保持向后兼容性",
                "migration_types": ["api_compatibility"],
                "estimated_files": self._count_files_by_type(analysis, "api_compatibility"),
                "risk_level": "medium",
            },
        ]

        return phases

    def _count_files_by_type(self, analysis: Dict[str, Any], migration_type: str) -> int:
        """统计指定迁移类型的文件数量"""
        count = 0
        for file_analysis in analysis["file_analyses"].values():
            for change in file_analysis.changes_required:
                if change.migration_type.value == migration_type:
                    count += 1
                    break
        return count

    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """生成迁移建议"""
        recommendations = []

        if analysis["risk_assessment"]["critical"] > 0:
            recommendations.append("存在关键风险文件，建议先在测试环境验证迁移方案")

        if analysis["migration_complexity"] == "high":
            recommendations.append("迁移复杂度较高，建议分阶段进行，每个阶段后进行充分测试")

        if analysis["total_changes_required"] > 1000:
            recommendations.append("代码变更量较大，建议使用自动化工具辅助迁移")

        recommendations.append("迁移前务必创建完整的数据和代码备份")
        recommendations.append("建议在迁移过程中进行功能验证测试")
        recommendations.append("迁移完成后进行性能对比测试")

        return recommendations


# 便捷函数
def analyze_project_code() -> Dict[str, Any]:
    """分析项目代码结构"""
    tools = CodeMigrationTools()
    return tools.analyze_project()


def apply_code_migration(migration_types: List[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """应用代码迁移"""
    tools = CodeMigrationTools()

    if migration_types:
        migration_types = [MigrationType(t) for t in migration_types]

    return tools.apply_migration(migration_types, dry_run)


def generate_migration_plan(output_file: str = "migration_plan.json") -> str:
    """生成迁移计划"""
    tools = CodeMigrationTools()
    return tools.generate_migration_plan(output_file)
