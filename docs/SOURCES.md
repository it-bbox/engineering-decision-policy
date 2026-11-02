# Первичные источники

Проверено 2 ноября 2026 года. Определения и демонстрационные пороги самого
комплекта — проектное соглашение, а не стандарт этих инструментов.

- [OpenAI: Customization](https://learn.chatgpt.com/docs/customization/overview) —
  различие постоянных AGENTS.md и повторно используемых skills, пути `.agents/skills`.
- [Claude Code: Skills](https://code.claude.com/docs/en/skills) —
  структура SKILL.md, проектные `.claude/skills` и явный вызов.
- [Claude Code: Memory](https://code.claude.com/docs/en/memory) — проектный CLAUDE.md.
- [SonarSource: Metrics](https://docs.sonarsource.com/sonarqube-server/user-guide/code-metrics/metrics-definition) —
  определения метрик сложности. AST-счётчик demo не является реализацией этих метрик.
- [Coverage.py: Branch coverage](https://coverage.readthedocs.io/en/latest/branch.html) —
  различие покрытия строк и ветвей; само покрытие не подтверждает качество assertions.
- [GitHub: Pages publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) —
  статическая публикация из ветки и выбранной папки.

Ни один источник не подтверждает эмпирическую эффективность именно этой политики.
Для неё предложен отдельный эксперимент в VERIFICATION.md.
