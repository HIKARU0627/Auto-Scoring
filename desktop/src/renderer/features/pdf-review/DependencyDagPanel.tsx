import { createContext, useContext, useMemo, useState, type JSX } from "react";
import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type {
  DagEdgeLine,
  DagNode,
  DependencyDagLayout,
} from "../../core/dependency-dag.js";

/**
 * 設問の選択（ノードのクリック / Enter / Space）を DAG のノードへ渡す。
 * React Flow のノード data はシリアライズ可能に保ちたいので、コールバックは
 * context で配る（`data` に関数を混ぜない）。
 */
const DagQuestionSelectContext = createContext<(questionId: string) => void>(
  () => {},
);

interface DagFlowNodeData extends Record<string, unknown> {
  readonly id: string;
  readonly label: string;
  readonly statusLabel: string;
}

type DagFlowNode = Node<DagFlowNodeData, "dagQuestion">;

/**
 * レイヤーが左→右、レイヤー内の並びが上→下。座標そのものは React Flow に
 * 渡す必要があるが、層の分け方は実行計画（`dependencyExecutionLayers`）が
 * 決めたもので、ここはその並びを px へ写すだけ。
 */
const LAYER_STEP_X = 220;
const ROW_STEP_Y = 88;

function DagQuestionNode({
  data,
  selected,
}: NodeProps<DagFlowNode>): JSX.Element {
  const onSelect = useContext(DagQuestionSelectContext);
  return (
    <div className="relative">
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: "var(--color-outline)",
          borderColor: "var(--color-surface-container-lowest)",
        }}
      />
      <button
        type="button"
        data-testid={`dag-node-${data.id}`}
        className={`w-40 rounded-md border px-md py-sm text-left ${
          selected
            ? "border-primary bg-primary-container/20"
            : "border-outline-variant bg-surface-container"
        }`}
        onClick={() => {
          onSelect(data.id);
        }}
      >
        <span className="block text-ui-label">問{data.label}</span>
        <span
          data-testid={`dag-node-status-${data.id}`}
          className="block text-body-small"
        >
          {data.statusLabel}
        </span>
      </button>
      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: "var(--color-primary)",
          borderColor: "var(--color-surface-container-lowest)",
        }}
      />
    </div>
  );
}

const nodeTypes = { dagQuestion: DagQuestionNode } satisfies NodeTypes;

function toFlowNode(
  node: DagNode,
  selectedQuestionId: string | null,
): DagFlowNode {
  return {
    id: node.question.id,
    type: "dagQuestion",
    position: { x: node.layer * LAYER_STEP_X, y: node.row * ROW_STEP_Y },
    selected: node.question.id === selectedQuestionId,
    draggable: false,
    focusable: false,
    data: {
      id: node.question.id,
      label: node.question.label,
      statusLabel: node.statusLabel,
    },
  };
}

function toFlowEdge(edge: DagEdgeLine): Edge {
  const stroke = edge.satisfied
    ? "var(--color-primary)"
    : "var(--color-outline)";
  return {
    id: edge.key,
    source: edge.fromQuestionId,
    target: edge.toQuestionId,
    type: "smoothstep",
    selectable: false,
    focusable: false,
    style: {
      stroke,
      strokeWidth: 2,
      ...(edge.satisfied ? {} : { strokeDasharray: "6 4" }),
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: stroke },
  };
}

export interface DependencyDagPanelProps {
  readonly layout: DependencyDagLayout;
  readonly selectedQuestionId: string | null;
  readonly onQuestionSelected: (questionId: string) => void;
}

export function DependencyDagPanel({
  layout,
  selectedQuestionId,
  onQuestionSelected,
}: DependencyDagPanelProps): JSX.Element {
  const [collapsed, setCollapsed] = useState(false);
  const nodes = useMemo(
    () => layout.nodes.map((node) => toFlowNode(node, selectedQuestionId)),
    [layout.nodes, selectedQuestionId],
  );
  const edges = useMemo(() => layout.edges.map(toFlowEdge), [layout.edges]);

  return (
    <section
      data-testid="dependency-dag-panel"
      className="flex flex-col gap-sm border border-outline-variant rounded-md p-md"
    >
      <header className="flex items-center justify-between gap-md">
        <p data-testid="dag-progress-summary" className="text-body-medium">
          {layout.progressSummary}
        </p>
        <button
          type="button"
          data-testid="dag-toggle-button"
          className="text-ui-label"
          onClick={() => {
            setCollapsed((value) => !value);
          }}
        >
          {collapsed ? "展開" : "畳む"}
        </button>
      </header>

      {layout.failures.map((failure) => (
        <div
          key={failure.openQuestionId}
          data-testid={`dag-failure-${failure.openQuestionId}`}
          className="flex flex-col gap-xs rounded-md border border-error/30 bg-error-container/20 p-sm"
        >
          <p
            data-testid={`dag-failure-headline-${failure.openQuestionId}`}
            className="text-body-medium font-medium"
          >
            {failure.headline}
          </p>
          <p className="text-body-small">{failure.guidance.cause}</p>
          <p
            data-testid={`dag-failure-next-${failure.openQuestionId}`}
            className="text-body-small"
          >
            {failure.guidance.nextStep}
          </p>
          <button
            type="button"
            data-testid={`dag-failure-open-${failure.openQuestionId}`}
            className="self-start rounded-md border border-outline px-md py-xs text-ui-label"
            onClick={() => {
              onQuestionSelected(failure.openQuestionId);
            }}
          >
            設問を開く
          </button>
        </div>
      ))}

      {!collapsed ? (
        <>
          {layout.edges.length === 0 ? (
            <p data-testid="dag-empty" className="text-body-small">
              依存関係はありません（すべて独立した設問）。
            </p>
          ) : null}
          <DagQuestionSelectContext.Provider value={onQuestionSelected}>
            <div style={{ height: "var(--layout-dag-flow-height)" }}>
              <ReactFlow<DagFlowNode, Edge>
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.4}
                maxZoom={1.6}
                nodesDraggable={false}
                nodesConnectable={false}
                proOptions={{ hideAttribution: true }}
                style={{
                  backgroundColor: "var(--color-surface-container-lowest)",
                }}
              >
                <Background color="var(--color-outline-variant)" gap={16} />
              </ReactFlow>
            </div>
          </DagQuestionSelectContext.Provider>
        </>
      ) : null}
    </section>
  );
}
