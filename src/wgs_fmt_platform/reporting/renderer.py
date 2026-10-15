from collections import defaultdict

from wgs_fmt_platform.contracts import StructuredReport


class MarkdownRenderer:
    def render(self, report: StructuredReport) -> str:
        lines = [
            f"# {report.title}",
            "",
            f"- 样本：{report.sample_id}",
            f"- 数据库版本：{report.versions.database.version}",
            f"- 知识版本：{report.versions.knowledge.version}",
            f"- 特征版本：{report.versions.features.version}",
            f"- 模型版本：{report.versions.model.version}",
            f"- 模板版本：{report.versions.report_template.version}",
        ]
        sections: dict[str, list[str]] = defaultdict(list)
        for statement in report.statements:
            sections[statement.section].append(statement.text)
        for section, statements in sections.items():
            lines.extend(["", f"## {section}", ""])
            lines.extend(f"- {statement}" for statement in statements)
        return "\n".join(lines) + "\n"

