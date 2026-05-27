import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Database,
  Loader2,
  Search,
  Table2,
  SquareTerminal,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { RuntimeDatabaseDescribeTableResponse } from "@/types/databaseConnectors";

interface SchemaGroup {
  schema: string;
  tables: string[];
  fullNames: string[];
}

function groupTablesBySchema(tables: string[]): SchemaGroup[] {
  const map = new Map<string, { tables: string[]; fullNames: string[] }>();
  for (const fullName of tables) {
    const dot = fullName.indexOf(".");
    if (dot > 0) {
      const schema = fullName.slice(0, dot);
      const name = fullName.slice(dot + 1);
      if (!map.has(schema)) map.set(schema, { tables: [], fullNames: [] });
      map.get(schema)!.tables.push(name);
      map.get(schema)!.fullNames.push(fullName);
    } else {
      if (!map.has("tables")) map.set("tables", { tables: [], fullNames: [] });
      map.get("tables")!.tables.push(fullName);
      map.get("tables")!.fullNames.push(fullName);
    }
  }
  return Array.from(map.entries()).map(([schema, { tables, fullNames }]) => ({
    schema,
    tables,
    fullNames,
  }));
}

function quoteIdentifier(ident: string): string {
  return `"${ident.replace(/"/g, "\"\"")}"`;
}

function quoteTableName(fullName: string): string {
  const dot = fullName.indexOf(".");
  if (dot > 0) {
    const schema = fullName.slice(0, dot);
    const name = fullName.slice(dot + 1);
    return `${quoteIdentifier(schema)}.${quoteIdentifier(name)}`;
  }
  return quoteIdentifier(fullName);
}

interface DatabaseSchemaTreeProps {
  tables: string[];
  selectedTable: string | null;
  expandedTables: Set<string>;
  expandedSchemas: Set<string>;
  loadingTables: boolean;
  loadingTableDetail: boolean;
  tableDetail: RuntimeDatabaseDescribeTableResponse | null;
  onTableSelect: (fullName: string) => void;
  onTableToggle: (fullName: string) => void;
  onSchemaToggle: (schema: string) => void;
  onGenerateQuery: (fullName: string) => void;
}

export function DatabaseSchemaTree({
  tables,
  selectedTable,
  expandedTables,
  expandedSchemas,
  loadingTables,
  loadingTableDetail,
  tableDetail,
  onTableSelect,
  onTableToggle,
  onSchemaToggle,
  onGenerateQuery,
}: DatabaseSchemaTreeProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredTables = useMemo(() => {
    if (!searchQuery.trim()) return tables;
    const q = searchQuery.trim().toLowerCase();
    return tables.filter((t) => t.toLowerCase().includes(q));
  }, [tables, searchQuery]);

  const schemaGroups = useMemo(() => {
    if (!filteredTables.length) return [];
    return groupTablesBySchema(filteredTables);
  }, [filteredTables]);

  const hasSchemas =
    schemaGroups.length > 1 ||
    (schemaGroups.length === 1 && schemaGroups[0].schema !== "tables");

  return (
    <div className="flex h-full flex-col bg-muted/20">
      <div className="flex-shrink-0 border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
          <Database className="h-3 w-3" />
          表结构
        </div>
        <div className="mt-2 relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索表..."
            className="h-7 pl-7 text-[11px]"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {loadingTables ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : schemaGroups.length > 0 ? (
          <div className="space-y-0.5 pt-1">
            {schemaGroups.map((group) => {
              const isSchemaExpanded = expandedSchemas.has(group.schema);
              if (!hasSchemas) {
                return group.tables.map((tableName, idx) => {
                  const fullName = group.fullNames[idx];
                  return (
                    <TableTreeItem
                      key={fullName}
                      fullName={fullName}
                      tableName={tableName}
                      isExpanded={expandedTables.has(fullName)}
                      isSelected={selectedTable === fullName}
                      isLoadingDetail={loadingTableDetail}
                      tableDetail={tableDetail}
                      onSelect={() => onTableSelect(fullName)}
                      onToggle={() => onTableToggle(fullName)}
                      onGenerateQuery={() => onGenerateQuery(fullName)}
                    />
                  );
                });
              }
              return (
                <div key={group.schema}>
                  <button
                    type="button"
                    onClick={() => onSchemaToggle(group.schema)}
                    className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-[12px] font-medium text-foreground hover:bg-muted transition-colors"
                  >
                    {isSchemaExpanded ? (
                      <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                    )}
                    <Database className="h-3 w-3 shrink-0 text-muted-foreground" />
                    <span className="truncate">{group.schema}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground/60">
                      {group.tables.length}
                    </span>
                  </button>
                  {isSchemaExpanded && (
                    <div className="ml-4 space-y-0.5">
                      {group.tables.map((tableName, idx) => {
                        const fullName = group.fullNames[idx];
                        return (
                          <TableTreeItem
                            key={fullName}
                            fullName={fullName}
                            tableName={tableName}
                            isExpanded={expandedTables.has(fullName)}
                            isSelected={selectedTable === fullName}
                            isLoadingDetail={loadingTableDetail}
                            tableDetail={tableDetail}
                            onSelect={() => onTableSelect(fullName)}
                            onToggle={() => onTableToggle(fullName)}
                            onGenerateQuery={() => onGenerateQuery(fullName)}
                          />
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="px-2 py-4 text-center text-[11px] text-muted-foreground/60">
            {searchQuery.trim() ? "无匹配的表" : "暂无数据表"}
          </div>
        )}
      </div>
    </div>
  );
}

interface TableTreeItemProps {
  fullName: string;
  tableName: string;
  isExpanded: boolean;
  isSelected: boolean;
  isLoadingDetail: boolean;
  tableDetail: RuntimeDatabaseDescribeTableResponse | null;
  onSelect: () => void;
  onToggle: () => void;
  onGenerateQuery: () => void;
}

function TableTreeItem({
  fullName,
  tableName,
  isExpanded,
  isSelected,
  isLoadingDetail,
  tableDetail,
  onSelect,
  onToggle,
  onGenerateQuery,
}: TableTreeItemProps) {
  return (
    <div>
      <div
        className={cn(
          "flex w-full items-center gap-0.5 rounded px-1.5 py-1 text-left text-[12px] transition-colors group",
          isSelected
            ? "bg-primary/10 text-primary"
            : "text-foreground hover:bg-muted"
        )}
      >
        <button
          type="button"
          onClick={onToggle}
          className="shrink-0 p-0.5 rounded hover:bg-muted-foreground/10"
        >
          {isExpanded ? (
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 text-muted-foreground" />
          )}
        </button>
        <button
          type="button"
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-center gap-1"
        >
          <Table2 className="h-3 w-3 shrink-0 text-muted-foreground" />
          <span className="truncate">{tableName}</span>
        </button>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onGenerateQuery();
          }}
          className="shrink-0 opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-muted-foreground/10 transition-opacity"
          title={`生成查询: SELECT * FROM ${quoteTableName(fullName)} LIMIT 100`}
        >
          <SquareTerminal className="h-3 w-3 text-muted-foreground" />
        </button>
      </div>
      {isExpanded && tableDetail?.table === fullName ? (
        <div className="ml-5 space-y-0.5 border-l border-border pl-2">
          {isLoadingDetail ? (
            <div className="py-1">
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            </div>
          ) : tableDetail.columns.length > 0 ? (
            tableDetail.columns.map((col) => (
              <div
                key={col.name}
                className="flex items-center gap-1 py-0.5 text-[11px] text-muted-foreground"
              >
                <span className="truncate">{col.name}</span>
                <span className="shrink-0 text-[10px] opacity-60">{col.type}</span>
                {!col.nullable && (
                  <span className="shrink-0 text-[10px] text-primary">NOT NULL</span>
                )}
              </div>
            ))
          ) : (
            <div className="py-1 text-[11px] text-muted-foreground/60">无列信息</div>
          )}
        </div>
      ) : null}
    </div>
  );
}
