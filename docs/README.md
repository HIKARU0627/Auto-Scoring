# docs

Operational docs for the agent development environment. Project-specific specs
(requirements, screens, architecture) go alongside these in your project.

| 文書                                                                             | 内容                                                                  |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| [ade-setup.md](./ade-setup.md)                                                   | Issue → 隔離worktree → 同一品質gate → PR の運用フローと責務分担       |
| [quality-gates.md](./quality-gates.md)                                           | `pnpm run check` の各gate、git hooks、CIの対応関係                    |
| [review-ready-skills.md](./review-ready-skills.md)                               | レビュー準備Skill群の構成・同期・エージェント間互換                   |
| [ai-agent-git-attribution.md](./ai-agent-git-attribution.md)                     | AIエージェントのコミット/pushを専用GitHub Appへ帰属させる手順（任意） |
| [mcp.md](./mcp.md)                                                               | MCPサーバー設定を3つのエージェント別ファイルへ展開する方法            |
| [business-rules-and-evaluation-data.md](./business-rules-and-evaluation-data.md) | 業務ルール・対象範囲・評価データの決定書（Issue #8）                  |
| [ai-grading-poc.md](./ai-grading-poc.md)                                         | PoC 2: AI採点精度と構造化出力の比較検証（Issue #14）                  |
| [schema/ai-grading-result.schema.json](./schema/ai-grading-result.schema.json)   | AI採点構造化出力 / 人間ラベルのデータ無しJSON Schema（§6.3）          |
