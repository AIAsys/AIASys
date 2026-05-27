import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type { GraphRenderData } from "./graphConfig";

export interface ForceNode extends SimulationNodeDatum {
  id: string;
  size: number;
}

export interface ForceLink extends SimulationLinkDatum<ForceNode> {
  id: string;
  strength: number;
}

export interface ForceLayoutState {
  nodes: ForceNode[];
  links: ForceLink[];
  nodeById: Map<string, ForceNode>;
  simulation: Simulation<ForceNode, ForceLink>;
}

function getInitialPosition(index: number, total: number, width: number, height: number) {
  const radius = Math.max(80, Math.min(width, height) * 0.22);
  const angle = (index / Math.max(total, 1)) * Math.PI * 2;
  return {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle) * radius,
  };
}

export function createForceLayout(
  graphData: GraphRenderData,
  width: number,
  height: number,
): ForceLayoutState {
  const nodes: ForceNode[] = graphData.nodes.map((node, index) => {
    const initialPosition = getInitialPosition(
      index,
      graphData.nodes.length,
      width,
      height,
    );

    return {
      id: node.id,
      size: node.data.size,
      x: initialPosition.x,
      y: initialPosition.y,
    };
  });
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const links: ForceLink[] = graphData.edges
    .filter((edge) => nodeById.has(edge.source) && nodeById.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      strength: edge.data.strength,
    }));

  const nodeCount = nodes.length;
  const linkDistance = nodeCount <= 18 ? 116 : nodeCount <= 48 ? 92 : 72;
  const chargeRange = Math.max(width, height) * (nodeCount <= 30 ? 1.4 : 1.05);
  const chargeStrength = nodeCount <= 18 ? -430 : nodeCount <= 60 ? -330 : -230;

  const simulation = forceSimulation<ForceNode>(nodes)
    .force(
      "link",
      forceLink<ForceNode, ForceLink>(links)
        .id((node) => node.id)
        .distance(linkDistance)
        .strength((link) => Math.min(0.86, Math.max(0.12, link.strength / 8))),
    )
    .force(
      "charge",
      forceManyBody<ForceNode>()
        .distanceMin(1)
        .distanceMax(chargeRange)
        .theta(0.5)
        .strength(chargeStrength),
    )
    .force(
      "collision",
      forceCollide<ForceNode>()
        .radius((node) => Math.max(24, node.size * 0.72))
        .iterations(2),
    )
    .force("x", forceX<ForceNode>(0).strength(0.02))
    .force("y", forceY<ForceNode>(0).strength(0.02))
    .force("center", forceCenter<ForceNode>(0, 0))
    .velocityDecay(0.5)
    .alpha(1)
    .alphaDecay(0.012)
    .alphaMin(0.02);
  simulation.stop();

  return { nodes, links, nodeById, simulation };
}
