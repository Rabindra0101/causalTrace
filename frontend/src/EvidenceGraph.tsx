
import { useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  Position,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

type EvidenceNode = {
  id: string
  type: string
  data: Record<string, unknown>
}

type EvidenceEdge = {
  source: string
  target: string
  relationship: string
}

type Props = {
  nodes: EvidenceNode[]
  edges: EvidenceEdge[]
}

function formatLabel(value: string) {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function formatCode(value: unknown) {
  return typeof value === 'number'
    ? String(value)
    : 'Unavailable'
}

function getNodeLabel(node: EvidenceNode) {
  if (node.type === 'failed_test') {
    const testName = String(node.data.test_name ?? node.id)
    return testName.split('::').pop() ?? testName
  }

  const labels: Record<string, string> = {
    test_failure: 'Test Failure',
    git_commit: 'Regression Commit',
    ai_hypothesis: 'Root Cause Hypothesis',
    experiment: 'Reversal Experiment',
  }

  return labels[node.type] ?? formatLabel(node.id)
}

function EvidenceDetails({ node }: { node: EvidenceNode }) {
  const data = node.data

  if (node.type === 'failed_test') {
    return (
      <div className="evidence-details">
        <h4>Individual Failed Test</h4>

        <p>
          <strong>Test identifier:</strong>
        </p>

        <code className="evidence-hash">
          {String(data.test_name ?? 'Unknown test')}
        </code>

        <p>
          <strong>Status: </strong>
          <span style={{ color: '#f87171' }}>
            {String(data.status ?? 'FAILED')}
          </span>
        </p>

        <p>
          This test failed during the investigation. Its
          failure contributes to the overall test failure
          evidence.
        </p>
      </div>
    )
  }

  if (node.type === 'experiment') {
    const verified = data.verified === true
    const beforeCode = data.before_return_code
    const afterCode = data.after_return_code

    return (
      <div className="evidence-details">
        <h4>Commit Reversal Verification</h4>

        <p>
          <strong>Verification result: </strong>
          <span style={{ color: verified ? '#4ade80' : '#fbbf24' }}>
            {verified ? 'REVERSAL VERIFIED' : 'INCONCLUSIVE'}
          </span>
        </p>

        <div className="experiment-results">
          <div className="experiment-result">
            <span>Before Reversal</span>
            <strong>
              {beforeCode === 0
                ? 'TEST PASSED'
                : typeof beforeCode === 'number'
                  ? 'TEST NOT PASSING'
                  : `Exit code: ${formatCode(beforeCode)}`}
            </strong>
            <small>Original suspected revision</small>
          </div>

          <div className="experiment-result">
            <span>After Reversal</span>
            <strong>
              {afterCode === 0
                ? 'TEST PASSED'
                : `Exit code: ${formatCode(afterCode)}`}
            </strong>
            <small>Suspected change reversed</small>
          </div>
        </div>

        <p>
          {verified
            ? 'Reversing the suspected change restored passing tests. This provides experimental evidence that the change contributed to the regression.'
            : 'The reversal experiment did not establish that the suspected change caused the test failure.'}
        </p>
      </div>
    )
  }

  if (node.type === 'git_commit') {
    return (
      <div className="evidence-details">
        <h4>Suspected Regression Commit</h4>

        <p>
          <strong>Commit hash:</strong>
        </p>

        <code className="evidence-hash">
          {String(data.hash ?? 'Unknown')}
        </code>

        <p>
          This commit was selected for investigation based on
          the observed regression and Git history.
        </p>
      </div>
    )
  }

  if (node.type === 'test_failure') {
    return (
      <div className="evidence-details">
        <h4>Observed Test Failure</h4>

        <p>
          <strong>Exit code:</strong>{' '}
          {formatCode(data.return_code)}
        </p>

        <pre className="evidence-output">
          {String(data.output ?? 'No test output available')}
        </pre>
      </div>
    )
  }

  if (node.type === 'ai_hypothesis') {
    return (
      <div className="evidence-details">
        <h4>NVIDIA Nemotron Hypothesis</h4>

        <p>
          <strong>Model:</strong>{' '}
          {String(data.model ?? 'Unknown')}
        </p>

        <p>
          This is the AI-generated explanation. Experimental
          verification is recorded separately.
        </p>

        <pre className="evidence-output">
          {String(data.explanation ?? 'No explanation available')}
        </pre>
      </div>
    )
  }

  return (
    <pre className="evidence-output">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

export default function EvidenceGraph({ nodes, edges }: Props) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    null
  )

  const selectedNode =
    nodes.find(node => node.id === selectedNodeId) ?? null

  const flowNodes = useMemo<Node[]>(() => {
    const mainOrder = [
      'test_failure',
      'regression_commit',
      'root_cause_hypothesis',
      'reversal_experiment',
    ]

    const mainNodes = mainOrder
      .map(id => nodes.find(node => node.id === id))
      .filter((node): node is EvidenceNode => node !== undefined)

    const failedTests = nodes.filter(
      node => node.type === 'failed_test'
    )

    const knownIds = new Set([
      ...mainNodes.map(node => node.id),
      ...failedTests.map(node => node.id),
    ])

    const otherNodes = nodes.filter(
      node => !knownIds.has(node.id)
    )

    const positions = new Map<string, { x: number; y: number }>()

    // Place individual failed tests above the main evidence chain.
    failedTests.forEach((node, index) => {
      positions.set(node.id, {
        x: (index - (failedTests.length - 1) / 2) * 310,
        y: 0,
      })
    })

    // Keep the four primary evidence nodes in a central chain.
    const mainStartY = failedTests.length > 0 ? 190 : 0

    mainNodes.forEach((node, index) => {
      positions.set(node.id, {
        x: 0,
        y: mainStartY + index * 170,
      })
    })

    otherNodes.forEach((node, index) => {
      positions.set(node.id, {
        x: 350,
        y: mainStartY + index * 170,
      })
    })

    return nodes.map(node => {
      const isFailedTest = node.type === 'failed_test'

      return {
        id: node.id,
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        data: {
          label: getNodeLabel(node),
        },
        style: {
          background: isFailedTest ? '#3b2230' : '#252e49',
          color: '#ffffff',
          border: isFailedTest
            ? '1px solid #f87171'
            : '1px solid #818cf8',
          borderRadius: '12px',
          padding: '18px',
          width: 260,
          fontWeight: 600,
          textAlign: 'center' as const,
          overflowWrap: 'anywhere' as const,
        },
      }
    })
  }, [nodes])

  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge, index) => ({
        id: `edge-${index}`,
        source: edge.source,
        target: edge.target,
        type: 'smoothstep',
        label: edge.relationship.replaceAll('_', ' '),
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: '#818cf8',
        },
        style: {
          stroke: '#818cf8',
          strokeWidth: 2,
        },
        labelStyle: {
          fill: '#cbd5e1',
          fontSize: 16,
        },
        labelBgStyle: {
          fill: '#252e49',
        },
        labelBgPadding: [8, 5],
        labelBgBorderRadius: 6,
      })),
    [edges]
  )

  return (
    <div>
      <div style={{ height: 650, width: '100%' }}>
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          colorMode="dark"
          onNodeClick={(_, clickedNode) => {
            setSelectedNodeId(clickedNode.id)
          }}
        >
          <Background color="#334155" gap={20} />
          <Controls />
        </ReactFlow>
      </div>

      {selectedNode && (
        <section className="evidence-inspector">
          <div className="evidence-inspector-header">
            <div>
              <h3>{getNodeLabel(selectedNode)}</h3>
              <p>
                Evidence type: {formatLabel(selectedNode.type)}
              </p>
            </div>

            <button
              type="button"
              className="evidence-close"
              onClick={() => setSelectedNodeId(null)}
            >
              Close
            </button>
          </div>

          <EvidenceDetails node={selectedNode} />
        </section>
      )}
    </div>
  )
}
