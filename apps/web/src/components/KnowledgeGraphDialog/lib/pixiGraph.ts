import {
  Application,
  Circle,
  Container,
  FederatedPointerEvent,
  Graphics,
  type Ticker,
} from "pixi.js";
import type { GraphRenderData, GraphRenderNode } from "./graphConfig";
import { getPreferredZoom } from "./graphConfig";
import {
  buildInteractionState,
} from "./graphInteractions";
import { createForceLayout, type ForceLayoutState, type ForceNode } from "./forceLayout";
import {
  applyEdgeVisualStates,
  applyNodeViewStyle,
  clamp,
  createNodeViewGraphics,
  getForceNodePosition,
  getNodeRadius,
  renderGraphPositions,
  type PixiEdgeView,
  type PixiNodeView,
} from "./pixiRenderer";

type Size = {
  width: number;
  height: number;
};

type Point = {
  x: number;
  y: number;
};

export interface PixiGraphViewport {
  zoomBy: (factor: number) => void;
  zoomTo: (scale: number) => void;
  fitToView: () => void;
  resetView: () => void;
  focusNode: (nodeId: string) => void;
}

interface PixiGraphOptions {
  container: HTMLDivElement;
  data: GraphRenderData;
  size: Size;
  selectedNodeId: string | null;
  searchQuery: string;
  onSelectNode: (nodeId: string | null) => void;
}

export class PixiGraphController implements PixiGraphViewport {
  private readonly app: Application;
  private readonly scene = new Container();
  private readonly edgeLayer = new Container();
  private readonly nodeLayer = new Container();
  private readonly labelLayer = new Container();
  private readonly onSelectNode: (nodeId: string | null) => void;
  private graphData: GraphRenderData;
  private size: Size;
  private forceLayout: ForceLayoutState | null = null;
  private nodeViews = new Map<string, PixiNodeView>();
  private edgeViews = new Map<string, PixiEdgeView>();
  private selectedNodeId: string | null;
  private searchQuery: string;
  private hoveredNodeId: string | null = null;
  private draggingNodeId: string | null = null;
  private nodePointerStart: Point | null = null;
  private didMoveDraggedNode = false;
  private isPanning = false;
  private panStart: Point | null = null;
  private sceneStart: Point | null = null;
  private isDestroyed = false;
  private tickerHandler: ((ticker: Ticker) => void) | null = null;
  private readonly handleWindowPointerUp = () => {
    this.endPointerAction();
  };
  private readonly handleWindowBlur = () => {
    this.endPointerAction();
  };
  private readonly handleWheel = (event: WheelEvent) => {
    event.preventDefault();
    const factor = Math.exp(-event.deltaY * 0.001);
    this.zoomAround(
      factor,
      {
        x: event.offsetX,
        y: event.offsetY,
      },
      false,
    );
  };

  private constructor(options: PixiGraphOptions, app: Application) {
    this.app = app;
    this.graphData = options.data;
    this.size = options.size;
    this.selectedNodeId = options.selectedNodeId;
    this.searchQuery = options.searchQuery;
    this.onSelectNode = options.onSelectNode;

    this.scene.sortableChildren = true;
    this.edgeLayer.zIndex = 1;
    this.nodeLayer.zIndex = 2;
    this.labelLayer.zIndex = 3;
    this.scene.addChild(this.edgeLayer, this.nodeLayer, this.labelLayer);
    this.app.stage.addChild(this.scene);
    this.setupCanvasEvents();
    this.rebuildGraph();
  }

  static async create(options: PixiGraphOptions): Promise<PixiGraphController> {
    const app = new Application();
    await app.init({
      width: options.size.width,
      height: options.size.height,
      antialias: true,
      autoDensity: true,
      backgroundAlpha: 0,
      preference: "webgl",
      resolution: Math.min(window.devicePixelRatio || 1, 2),
      powerPreference: "high-performance",
    });
    app.canvas.className = "h-full w-full";
    options.container.appendChild(app.canvas);
    return new PixiGraphController(options, app);
  }

  destroy() {
    this.isDestroyed = true;
    this.stopSimulation();
    this.app.canvas.removeEventListener("wheel", this.handleWheel);
    window.removeEventListener("pointerup", this.handleWindowPointerUp);
    window.removeEventListener("blur", this.handleWindowBlur);
    this.app.destroy({ removeView: true }, { children: true });
  }

  setSize(size: Size) {
    if (this.isDestroyed || size.width <= 0 || size.height <= 0) {
      return;
    }
    if (this.size.width === size.width && this.size.height === size.height) {
      return;
    }

    this.size = size;
    this.app.renderer.resize(size.width, size.height);
    if (this.scene.scale.x === 1 && this.scene.position.x === 0) {
      this.fitToView();
    }
  }

  setData(data: GraphRenderData) {
    this.graphData = data;
    this.rebuildGraph();
  }

  setInteractionState(selectedNodeId: string | null, searchQuery: string) {
    this.selectedNodeId = selectedNodeId;
    this.searchQuery = searchQuery;
    this.applyVisualState();
  }

  zoomBy(factor: number) {
    this.zoomAround(
      factor,
      {
        x: this.size.width / 2,
        y: this.size.height / 2,
      },
      true,
    );
  }

  zoomTo(scale: number) {
    const currentScale = this.scene.scale.x || 1;
    this.zoomBy(scale / currentScale);
  }

  fitToView() {
    if (!this.forceLayout?.nodes.length) {
      this.scene.scale.set(1);
      this.scene.position.set(this.size.width / 2, this.size.height / 2);
      return;
    }

    const bounds = this.getGraphBounds();
    if (!bounds) {
      return;
    }

    const padding = 88;
    const width = Math.max(1, bounds.maxX - bounds.minX);
    const height = Math.max(1, bounds.maxY - bounds.minY);
    const availableWidth = Math.max(1, this.size.width - padding * 2);
    const availableHeight = Math.max(1, this.size.height - padding * 2);
    const fitScale = Math.min(availableWidth / width, availableHeight / height);
    const preferredZoom = getPreferredZoom(this.forceLayout.nodes.length);
    const scale = clamp(Math.min(fitScale, preferredZoom), 0.2, 2.4);
    const centerX = (bounds.minX + bounds.maxX) / 2;
    const centerY = (bounds.minY + bounds.maxY) / 2;

    this.scene.scale.set(scale);
    this.scene.position.set(
      this.size.width / 2 - centerX * scale,
      this.size.height / 2 - centerY * scale,
    );
  }

  resetView() {
    this.scene.scale.set(1);
    this.scene.position.set(this.size.width / 2, this.size.height / 2);
  }

  focusNode(nodeId: string) {
    const node = this.forceLayout?.nodeById.get(nodeId);
    if (!node) {
      return;
    }
    const position = getForceNodePosition(node);
    const targetScale = clamp(Math.max(this.scene.scale.x, 1.18), 0.35, 2.2);
    this.scene.scale.set(targetScale);
    this.scene.position.set(
      this.size.width / 2 - position.x * targetScale,
      this.size.height / 2 - position.y * targetScale,
    );
  }

  private rebuildGraph() {
    this.stopSimulation();
    this.edgeLayer.removeChildren().forEach((child) => child.destroy());
    this.nodeLayer.removeChildren().forEach((child) => child.destroy());
    this.labelLayer.removeChildren().forEach((child) => child.destroy());
    this.nodeViews.clear();
    this.edgeViews.clear();

    this.forceLayout = createForceLayout(
      this.graphData,
      this.size.width,
      this.size.height,
    );

    for (const edge of this.graphData.edges) {
      if (!this.forceLayout.nodeById.has(edge.source) || !this.forceLayout.nodeById.has(edge.target)) {
        continue;
      }
      const line = new Graphics();
      line.zIndex = 1;
      this.edgeLayer.addChild(line);
      this.edgeViews.set(edge.id, {
        id: edge.id,
        sourceId: edge.source,
        targetId: edge.target,
        line,
      });
    }

    for (const node of this.graphData.nodes) {
      const forceNode = this.forceLayout.nodeById.get(node.id);
      if (!forceNode) {
        continue;
      }
      const nodeView = this.createNodeView(node, forceNode);
      this.nodeViews.set(node.id, nodeView);
      this.nodeLayer.addChild(nodeView.root);
      this.labelLayer.addChild(nodeView.label);
    }

    this.tickerHandler = () => {
      this.forceLayout?.simulation.tick();
      this.renderGraph();
      const simulation = this.forceLayout?.simulation;
      if (simulation && simulation.alpha() <= simulation.alphaMin()) {
        simulation.alpha(0.035);
      }
    };
    this.app.ticker.add(this.tickerHandler);
    this.renderGraph();
    this.fitToView();
    this.applyVisualState();
  }

  private createNodeView(node: GraphRenderNode, forceNode: ForceNode): PixiNodeView {
    const radius = getNodeRadius(node);
    const root = new Container();
    const { halo, body, label } = createNodeViewGraphics(node);

    root.addChild(halo, body);
    root.eventMode = "dynamic";
    root.cursor = "grab";
    root.hitArea = new Circle(0, 0, Math.max(18, radius + 8));
    root.on("pointerdown", (event: FederatedPointerEvent) => {
      event.stopPropagation();
      this.handleNodePointerDown(event, node.id, forceNode);
    });
    root.on("pointerover", () => {
      this.hoveredNodeId = node.id;
      this.applyVisualState();
    });
    root.on("pointerout", () => {
      if (this.hoveredNodeId === node.id) {
        this.hoveredNodeId = null;
        this.applyVisualState();
      }
    });

    return { node, forceNode, root, halo, body, label };
  }

  private handleNodePointerDown(
    event: FederatedPointerEvent,
    nodeId: string,
    _forceNode: ForceNode,
  ) {
    this.draggingNodeId = nodeId;
    this.nodePointerStart = { x: event.global.x, y: event.global.y };
    this.didMoveDraggedNode = false;
    const nodeView = this.nodeViews.get(nodeId);
    if (nodeView) {
      nodeView.root.cursor = "grabbing";
    }
  }

  private setupCanvasEvents() {
    this.app.stage.eventMode = "static";
    this.app.stage.hitArea = this.app.screen;

    this.app.stage.on("pointerdown", (event: FederatedPointerEvent) => {
      if (this.draggingNodeId) {
        return;
      }
      this.isPanning = true;
      this.panStart = { x: event.global.x, y: event.global.y };
      this.sceneStart = {
        x: this.scene.position.x,
        y: this.scene.position.y,
      };
      this.onSelectNode(null);
    });

    this.app.stage.on("globalpointermove", (event: FederatedPointerEvent) => {
      if (this.draggingNodeId) {
        const node = this.forceLayout?.nodeById.get(this.draggingNodeId);
        if (!node) {
          return;
        }
        if (this.nodePointerStart) {
          const deltaX = event.global.x - this.nodePointerStart.x;
          const deltaY = event.global.y - this.nodePointerStart.y;
          this.didMoveDraggedNode ||= Math.hypot(deltaX, deltaY) > 4;
        }
        const local = event.getLocalPosition(this.scene);
        node.fx = local.x;
        node.fy = local.y;
        this.forceLayout?.simulation.alphaTarget(0.3).restart();
        return;
      }

      if (!this.isPanning || !this.panStart || !this.sceneStart) {
        return;
      }
      this.scene.position.set(
        this.sceneStart.x + event.global.x - this.panStart.x,
        this.sceneStart.y + event.global.y - this.panStart.y,
      );
    });

    this.app.stage.on("globalpointerup", () => {
      this.endPointerAction();
    });
    this.app.stage.on("globalpointerupoutside", () => {
      this.endPointerAction();
    });

    this.app.canvas.addEventListener("wheel", this.handleWheel, { passive: false });
    window.addEventListener("pointerup", this.handleWindowPointerUp);
    window.addEventListener("blur", this.handleWindowBlur);
  }

  private endPointerAction() {
    if (this.draggingNodeId) {
      const node = this.forceLayout?.nodeById.get(this.draggingNodeId);
      if (node) {
        node.fx = undefined;
        node.fy = undefined;
      }
      const nodeView = this.nodeViews.get(this.draggingNodeId);
      if (nodeView) {
        nodeView.root.cursor = "grab";
      }
      if (this.didMoveDraggedNode) {
        this.onSelectNode(null);
      } else {
        this.onSelectNode(
          this.selectedNodeId === this.draggingNodeId ? null : this.draggingNodeId,
        );
      }
      this.forceLayout?.simulation.alphaTarget(0);
    }
    this.draggingNodeId = null;
    this.nodePointerStart = null;
    this.didMoveDraggedNode = false;
    this.isPanning = false;
    this.panStart = null;
    this.sceneStart = null;
  }

  private renderGraph() {
    renderGraphPositions(this.edgeViews, this.nodeViews, this.forceLayout);
  }

  private applyVisualState() {
    const interactionState = buildInteractionState(
      this.graphData,
      this.selectedNodeId,
      this.searchQuery,
    );

    const currentScale = this.scene.scale.x || 1;
    for (const nodeView of this.nodeViews.values()) {
      applyNodeViewStyle(
        nodeView,
        interactionState,
        this.selectedNodeId,
        this.hoveredNodeId,
        currentScale,
      );
    }

    applyEdgeVisualStates(this.edgeViews, interactionState);
  }

  private stopSimulation() {
    if (this.tickerHandler) {
      this.app.ticker.remove(this.tickerHandler);
      this.tickerHandler = null;
    }
    this.forceLayout?.simulation.stop();
    this.forceLayout = null;
  }

  private zoomAround(factor: number, screenPoint: Point, animate: boolean) {
    void animate;
    const currentScale = this.scene.scale.x || 1;
    const nextScale = clamp(currentScale * factor, 0.18, 4.2);
    const worldPoint = {
      x: (screenPoint.x - this.scene.position.x) / currentScale,
      y: (screenPoint.y - this.scene.position.y) / currentScale,
    };

    this.scene.scale.set(nextScale);
    this.scene.position.set(
      screenPoint.x - worldPoint.x * nextScale,
      screenPoint.y - worldPoint.y * nextScale,
    );
  }

  private getGraphBounds() {
    if (!this.forceLayout?.nodes.length) {
      return null;
    }

    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;

    for (const node of this.forceLayout.nodes) {
      const position = getForceNodePosition(node);
      minX = Math.min(minX, position.x);
      minY = Math.min(minY, position.y);
      maxX = Math.max(maxX, position.x);
      maxY = Math.max(maxY, position.y);
    }

    return { minX, minY, maxX, maxY };
  }
}
