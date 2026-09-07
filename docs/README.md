# docs

Operational docs for the agent development environment. Project-specific specs
(requirements, screens, architecture) go alongside these in your project.

| 文書                                                         | 内容                                                                     |
| ------------------------------------------------------------ | ------------------------------------------------------------------------ |
| [ade-setup.md](./ade-setup.md)                               | Issue → 隔離worktree → 同一品質gate → PR の運用フローと責務分担          |
| [quality-gates.md](./quality-gates.md)                       | `pnpm run check` の各gate、git hooks、CIの対応関係                       |
| [review-ready-skills.md](./review-ready-skills.md)           | レビュー準備Skill群の構成・同期・エージェント間互換                      |
| [ai-agent-git-attribution.md](./ai-agent-git-attribution.md) | AIエージェントのコミット/pushを専用GitHub Appへ帰属させる手順（任意）    |
| [mcp.md](./mcp.md)                                           | MCPサーバー設定を3つのエージェント別ファイルへ展開する方法               |
| [orca-remote-environment.md](./orca-remote-environment.md)   | Windows の Orca から Ubuntu 上の Orca ランタイムへ接続する構築・運用手順 |
| [windows-distribution.md](./windows-distribution.md)         | Windows 配布物・サイドカーのライフサイクル・障害復旧・署名手順           |
