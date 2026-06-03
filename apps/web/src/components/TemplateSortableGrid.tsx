import { useEffect, useState } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  rectSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Eye, FilePlus, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";
import { TEMPLATE_ICON_MAP } from "@/lib/templateIcons";
import type { WorkspaceTemplateItem } from "@/lib/api/workspaces";

const ENV_LABEL_MAP: Record<string, string> = {
  none: "不启用 Python",
  uv: "Python 环境",
  registered: "已登记 Python",
  docker: "Docker",
};

interface SortableTemplateCardProps {
  template: WorkspaceTemplateItem;
  isSelected: boolean;
  isBusy: boolean;
  onSelect: (templateId: string) => void;
  onPreview: (template: WorkspaceTemplateItem) => void;
}

function SortableTemplateCard({
  template,
  isSelected,
  isBusy,
  onSelect,
  onPreview,
}: SortableTemplateCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: template.template_id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "relative flex flex-col items-center gap-1.5 rounded-lg border px-2 py-3 text-center transition-colors",
        isSelected
          ? "border-primary bg-primary/5"
          : "border-border bg-background hover:bg-muted/50",
        isBusy && "cursor-not-allowed opacity-60",
        isDragging && "opacity-60 shadow-lg",
      )}
    >
      {/* 拖拽手柄 */}
      <span
        {...attributes}
        {...listeners}
        className="absolute left-1 top-1 flex h-5 w-5 cursor-grab items-center justify-center rounded text-muted-foreground/50 transition-colors hover:bg-muted hover:text-muted-foreground active:cursor-grabbing"
        title="拖拽排序"
      >
        <GripVertical className="h-3 w-3" />
      </span>

      {/* 预览按钮 */}
      {template.template_id !== "blank-workspace" &&
        template.files &&
        template.files.length > 0 && (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              onPreview(template);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.stopPropagation();
                onPreview(template);
              }
            }}
            className="absolute right-1.5 top-1.5 flex h-5 w-5 cursor-pointer items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title="预览模板"
          >
            <Eye className="h-3 w-3" />
          </span>
        )}

      {/* 点击选区 */}
      <button
        type="button"
        onClick={() => onSelect(template.template_id)}
        disabled={isBusy}
        className="flex flex-col items-center gap-1.5"
      >
        <div
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
            isSelected
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground",
          )}
        >
          {TEMPLATE_ICON_MAP[template.icon] ?? <FilePlus className="h-5 w-5" />}
        </div>
        <div className="min-w-0">
          <div className="text-xs font-medium">{template.name}</div>
          {template.env_kind && template.env_kind !== "none" && (
            <div className="mt-0.5 text-[10px] text-muted-foreground">
              {ENV_LABEL_MAP[template.env_kind] ?? template.env_kind}
            </div>
          )}
        </div>
      </button>
    </div>
  );
}

interface TemplateSortableGridProps {
  templates: WorkspaceTemplateItem[];
  selectedTemplateId: string;
  isBusy: boolean;
  onSelect: (templateId: string) => void;
  onPreview: (template: WorkspaceTemplateItem) => void;
  onReorder: (newOrder: WorkspaceTemplateItem[]) => void;
}

export function TemplateSortableGrid({
  templates,
  selectedTemplateId,
  isBusy,
  onSelect,
  onPreview,
  onReorder,
}: TemplateSortableGridProps) {
  const [items, setItems] = useState(templates);

  // 外部 templates 变化时同步内部状态
  useEffect(() => {
    setItems(templates);
  }, [templates]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = items.findIndex((t) => t.template_id === active.id);
    const newIndex = items.findIndex((t) => t.template_id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const newItems = arrayMove(items, oldIndex, newIndex);
    setItems(newItems);
    onReorder(newItems);
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext
        items={items.map((t) => t.template_id)}
        strategy={rectSortingStrategy}
      >
        <div className="grid grid-cols-3 gap-2">
          {items.map((template) => (
            <SortableTemplateCard
              key={template.template_id}
              template={template}
              isSelected={selectedTemplateId === template.template_id}
              isBusy={isBusy}
              onSelect={onSelect}
              onPreview={onPreview}
            />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}
