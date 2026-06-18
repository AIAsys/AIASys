/**
 * KnowledgeBaseMarket - 知识库市场/管理组件
 *
 * 支持：
 * - dialog 模式：弹窗承载
 * - page 模式：独立路由页承载
 */

import { useEffect, useMemo, useRef, useState, lazy, Suspense } from "react";
import { cn } from "@/lib/utils";
import { knowledgeApi } from "@/lib/api/knowledge";
import { getModelDefaults, getModels, type LLMModelConfig } from "@/lib/api/llm";
import type {
  Document,
  KnowledgeBase,
  KnowledgeBaseExtractionMode,
  KnowledgeBaseSearchMode,
  UpdateKnowledgeBaseRequest,
  UploadDocumentResponse,
} from "@/types/knowledge";
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { KBListPane } from "./KBListPane";
import { KBDetailPane, KBDetailEmpty } from "./KBDetailPane";
import { DeleteConfirmDialog } from "./KBDialogs";

const CreateDialog = lazy(() =>
  import("./KBDialogs").then((module) => ({ default: module.CreateDialog })),
);
const UploadDialog = lazy(() =>
  import("./KBDialogs").then((module) => ({ default: module.UploadDialog })),
);
const QueryDialog = lazy(() =>
  import("./KBDialogs").then((module) => ({ default: module.QueryDialog })),
);
import { normalizeSearchMode } from "./constants";

interface KnowledgeBaseMarketProps {
  open?: boolean;
  onClose?: () => void;
  mode?: "dialog" | "page";
  pageLayout?: "grid" | "split";
  visibleKnowledgeBaseIds?: string[] | null;
  defaultKnowledgeBaseId?: string | null;
  listTitle?: string;
  listDescription?: string;
  allowCreate?: boolean;
  onSelectKnowledgeBaseIdChange?: (knowledgeBaseId: string | null) => void;
}

export function KnowledgeBaseMarket({
  open = false,
  onClose,
  mode = "dialog",
  pageLayout = "grid",
  visibleKnowledgeBaseIds = null,
  defaultKnowledgeBaseId = null,
  listTitle = "我的知识库",
  listDescription = "管理您的知识库，上传文档并进行智能检索",
  allowCreate = true,
  onSelectKnowledgeBaseIdChange,
}: KnowledgeBaseMarketProps) {
  const isPageMode = mode === "page";
  const isSplitLayout = pageLayout === "split";
  const isActive = isPageMode || open;

  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [embeddingModels, setEmbeddingModels] = useState<LLMModelConfig[]>([]);
  const [defaultEmbeddingModelId, setDefaultEmbeddingModelId] = useState<string | null>(null);
  const [isLoadingModels, setIsLoadingModels] = useState(false);

  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createEmbeddingModel, setCreateEmbeddingModel] = useState("");
  const [createSearchMode, setCreateSearchMode] = useState<KnowledgeBaseSearchMode>("fulltext");
  const [createChunkSize, setCreateChunkSize] = useState("512");
  const [createChunkOverlap, setCreateChunkOverlap] = useState("50");
  const [isCreating, setIsCreating] = useState(false);

  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [uploadExtractionMode, setUploadExtractionMode] = useState<KnowledgeBaseExtractionMode>("enhanced");
  const [uploadEmbeddingModel, setUploadEmbeddingModel] = useState("");
  const [uploadSearchMode, setUploadSearchMode] = useState<KnowledgeBaseSearchMode>("fulltext");
  const [uploadChunkSize, setUploadChunkSize] = useState("512");
  const [uploadChunkOverlap, setUploadChunkOverlap] = useState("50");
  const [uploadResults, setUploadResults] = useState<UploadDocumentResponse[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const uploadAbortRef = useRef<AbortController | null>(null);


  const [isQueryOpen, setIsQueryOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteKind, setDeleteKind] = useState<"kb" | "doc">("kb");
  const [deleteTargetId, setDeleteTargetId] = useState<string>("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [queryText, setQueryText] = useState("");
  const [queryResults, setQueryResults] = useState<Array<{ content: string; score: number }>>([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [querySearchMode, setQuerySearchMode] = useState<KnowledgeBaseSearchMode>(() => {
    try {
      const saved = localStorage.getItem("kb-search-mode");
      if (saved === "fulltext" || saved === "vector" || saved === "hybrid") return saved;
    } catch { /* ignore */ }
    return "fulltext";
  });

  const loadKnowledgeBases = async () => {
    setIsLoadingList(true);
    try {
      const data = await knowledgeApi.listKnowledgeBases();
      setKnowledgeBases(data);
    } catch (err) {
      console.error("加载知识库失败:", err);
    } finally {
      setIsLoadingList(false);
    }
  };

  const loadEmbeddingModels = async () => {
    setIsLoadingModels(true);
    try {
      const [modelsResponse, defaults] = await Promise.all([
        getModels(true),
        getModelDefaults(),
      ]);
      setEmbeddingModels(modelsResponse.models.filter((model) => model.model_type === "embedding"));
      setDefaultEmbeddingModelId(defaults.default_embedding_model);
    } catch (err) {
      console.error("加载 embedding 模型失败:", err);
      setEmbeddingModels([]);
      setDefaultEmbeddingModelId(null);
    } finally {
      setIsLoadingModels(false);
    }
  };

  const resetCreateForm = () => {
    setCreateName("");
    setCreateDescription("");
    setCreateEmbeddingModel(defaultEmbeddingModelId || "");
    setCreateSearchMode("fulltext");
    setCreateChunkSize("512");
    setCreateChunkOverlap("50");
  };

  const openCreateDialog = () => {
    setCreateName("");
    setCreateDescription("");
    setCreateEmbeddingModel(defaultEmbeddingModelId || "");
    setCreateSearchMode("fulltext");
    setCreateChunkSize("512");
    setCreateChunkOverlap("50");
    setIsCreateOpen(true);
  };

  const openUploadDialog = () => {
    if (!selectedKB) return;
    if (!selectedKB.config_complete || selectedKB.init_status !== "ready") {
      alert(selectedKB.config_issue || "需要先配置模型");
      return;
    }
    setUploadFiles([]);
    setUploadProgress({});
    setUploadResults([]);
    setUploadExtractionMode("enhanced");
    setUploadEmbeddingModel(selectedKB.embedding_model || defaultEmbeddingModelId || "");
    setUploadSearchMode(normalizeSearchMode(selectedKB.default_search_mode));
    setUploadChunkSize(String(selectedKB.chunk_size || 512));
    setUploadChunkOverlap(String(selectedKB.chunk_overlap || 50));
    setIsUploadOpen(true);
  };

  useEffect(() => {
    if (isActive) {
      void loadKnowledgeBases();
      void loadEmbeddingModels();
      return;
    }
    setSelectedKB(null);
    setSearchQuery("");
  }, [isActive]);

  // 组件卸载时取消正在进行的上传请求
  useEffect(() => {
    return () => {
      uploadAbortRef.current?.abort();
    };
  }, []);

  const scopedKnowledgeBases = useMemo(
    () =>
      Array.isArray(visibleKnowledgeBaseIds)
        ? knowledgeBases.filter((kb) => visibleKnowledgeBaseIds.includes(kb.id))
        : knowledgeBases,
    [knowledgeBases, visibleKnowledgeBaseIds],
  );

  const filteredKBs = useMemo(() => {
    if (!searchQuery) return scopedKnowledgeBases;
    const query = searchQuery.toLowerCase();
    return scopedKnowledgeBases.filter(
      (kb) =>
        kb.name.toLowerCase().includes(query) ||
        (kb.description?.toLowerCase() || "").includes(query),
    );
  }, [scopedKnowledgeBases, searchQuery]);

  useEffect(() => {
    if (!defaultKnowledgeBaseId) return;
    const matched = knowledgeBases.find((kb) => kb.id === defaultKnowledgeBaseId);
    if (!matched || selectedKB?.id === matched.id) return;
    void openDetail(matched);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultKnowledgeBaseId, knowledgeBases]);

  useEffect(() => {
    if (!isSplitLayout || selectedKB?.id || defaultKnowledgeBaseId) return;
    const first = scopedKnowledgeBases[0];
    if (!first) return;
    void openDetail(first);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultKnowledgeBaseId, isSplitLayout, scopedKnowledgeBases]);

  useEffect(() => {
    if (!selectedKB || !Array.isArray(visibleKnowledgeBaseIds)) return;
    if (visibleKnowledgeBaseIds.includes(selectedKB.id)) return;
    setSelectedKB(null);
    setDocuments([]);
  }, [selectedKB, selectedKB?.id, visibleKnowledgeBaseIds]);

  useEffect(() => {
    if (!isCreateOpen) return;
    setCreateEmbeddingModel((current) => current || defaultEmbeddingModelId || "");
  }, [defaultEmbeddingModelId, isCreateOpen]);

  const handleCreate = async () => {
    if (!createName.trim()) return;
    const chunkSize = Number.parseInt(createChunkSize, 10) || 512;
    const chunkOverlap = Number.parseInt(createChunkOverlap, 10) || 50;
    if (chunkOverlap >= chunkSize) {
      alert("分块重叠必须小于分块大小");
      return;
    }
    setIsCreating(true);
    try {
      await knowledgeApi.createKnowledgeBase({
        name: createName.trim(),
        description: createDescription.trim() || undefined,
        embedding_model: createEmbeddingModel || undefined,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        default_search_mode: createSearchMode,
      });
      setIsCreateOpen(false);
      resetCreateForm();
      await loadKnowledgeBases();
    } catch (err) {
      alert(err instanceof Error ? err.message : "创建失败");
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteKB = async (id: string) => {
    setDeleteKind("kb");
    setDeleteTargetId(id);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    setIsDeleting(true);
    if (deleteKind === "kb") {
      try {
        await knowledgeApi.deleteKnowledgeBase(deleteTargetId);
        setDeleteDialogOpen(false);
        await loadKnowledgeBases();
      } catch (err) {
        alert(err instanceof Error ? err.message : "删除失败");
      } finally {
        setIsDeleting(false);
      }
    } else {
      if (!selectedKB) {
        setIsDeleting(false);
        return;
      }
      try {
        await knowledgeApi.deleteDocument(selectedKB.id, deleteTargetId);
        setDeleteDialogOpen(false);
        const docs = await knowledgeApi.listDocuments(selectedKB.id);
        setDocuments(docs);
        await loadKnowledgeBases();
      } catch (err) {
        alert(err instanceof Error ? err.message : "删除失败");
      } finally {
        setIsDeleting(false);
      }
    }
  };

  const handleUpdateKBConfig = async (
    kbId: string,
    payload: UpdateKnowledgeBaseRequest,
  ) => {
    await knowledgeApi.updateKnowledgeBase(kbId, payload);
    const refreshed = await knowledgeApi.getKnowledgeBase(kbId);
    setSelectedKB(refreshed);
    await loadKnowledgeBases();
  };

  const openDetail = async (kb: KnowledgeBase) => {
    setSelectedKB(kb);
    onSelectKnowledgeBaseIdChange?.(kb.id);
    setIsLoadingDocs(true);
    try {
      const docs = await knowledgeApi.listDocuments(kb.id);
      setDocuments(docs);
    } catch (err) {
      console.error("加载文档失败:", err);
    } finally {
      setIsLoadingDocs(false);
    }
  };

  const backToList = () => {
    setSelectedKB(null);
    setDocuments([]);
    onSelectKnowledgeBaseIdChange?.(null);
    void loadKnowledgeBases();
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setUploadFiles((prev) => [...prev, ...files]);
    const nextProgress: Record<string, number> = {};
    files.forEach((file) => {
      nextProgress[file.name] = 0;
    });
    setUploadProgress((prev) => ({ ...prev, ...nextProgress }));
  };

  const handleRemoveFile = (fileName: string) => {
    setUploadFiles((prev) => prev.filter((f) => f.name !== fileName));
    setUploadProgress((prev) => {
      const next = { ...prev };
      delete next[fileName];
      return next;
    });
  };

  const handleUpload = async () => {
    if (!selectedKB || uploadFiles.length === 0) return;
    if (!selectedKB.config_complete || selectedKB.init_status !== "ready") {
      alert(selectedKB.config_issue || "需要先配置模型");
      return;
    }
    const spreadsheetFiles = uploadFiles.filter(
      (f) => f.name.toLowerCase().endsWith(".xlsx") || f.name.toLowerCase().endsWith(".xlsm"),
    );
    if (spreadsheetFiles.length > 0) {
      alert(`表格文件(${spreadsheetFiles.map((f) => f.name).join(", ")})建议放到工作区处理，知识库对表格数据的检索效果有限`);
      return;
    }
    const chunkSize = Number.parseInt(uploadChunkSize, 10) || (selectedKB.chunk_size || 512);
    const chunkOverlap = Number.parseInt(uploadChunkOverlap, 10) || (selectedKB.chunk_overlap || 50);
    if (chunkOverlap >= chunkSize) {
      alert("分块重叠必须小于分块大小");
      return;
    }
    setIsUploading(true);
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    try {
      uploadFiles.forEach((file) => {
        setUploadProgress((prev) => ({ ...prev, [file.name]: 35 }));
      });
      const response = await knowledgeApi.uploadDocuments(
        selectedKB.id,
        uploadFiles,
        {
          extraction_mode: uploadExtractionMode,
          embedding_model: documents.length === 0 ? uploadEmbeddingModel : undefined,
          chunk_size: chunkSize,
          chunk_overlap: chunkOverlap,
          search_mode: uploadSearchMode,
        },
        controller.signal,
      );
      response.results.forEach((result) => {
        setUploadProgress((prev) => ({
          ...prev,
          [result.filename]: result.success ? 100 : 0,
        }));
      });
      setUploadResults(response.results);
      setUploadFiles([]);
      const docs = await knowledgeApi.listDocuments(selectedKB.id);
      setDocuments(docs);
      await loadKnowledgeBases();
      const refreshed = await knowledgeApi.getKnowledgeBase(selectedKB.id);
      setSelectedKB(refreshed);
      if (response.failed_count === 0) {
        setIsUploadOpen(false);
        setUploadProgress({});
      }
    } catch (err) {
      if (controller.signal.aborted) {
        // 用户主动取消，不弹错误提示
        setUploadProgress({});
        setIsUploadOpen(false);
      } else {
        alert(err instanceof Error ? err.message : "上传失败");
      }
    } finally {
      uploadAbortRef.current = null;
      setIsUploading(false);
    }
  };

  const handleCancelUpload = () => {
    uploadAbortRef.current?.abort();
  };

  const handleDeleteDoc = async (docId: string) => {
    if (!selectedKB) return;
    setDeleteKind("doc");
    setDeleteTargetId(docId);
    setDeleteDialogOpen(true);
  };

  const handleQuery = async () => {
    if (!selectedKB || !queryText.trim()) return;
    if (!selectedKB.config_complete || selectedKB.init_status !== "ready") {
      alert(selectedKB.config_issue || "需要先配置模型");
      return;
    }
    setIsQuerying(true);
    try {
      const response = await knowledgeApi.query(selectedKB.id, {
        query: queryText.trim(),
        top_k: 5,
        search_mode: querySearchMode,
      });
      setQueryResults(response.results);
    } catch (err) {
      console.error("检索失败:", err);
    } finally {
      setIsQuerying(false);
    }
  };

  const documentChunkCount = documents.reduce(
    (sum, document) => sum + (document.chunk_count || 0),
    0,
  );

  // 当存在正在构建索引的文档时，自动轮询刷新文档列表
  const hasIndexingDocuments = documents.some(
    (doc) => doc.status === "pending" || doc.status === "processing",
  );
  useEffect(() => {
    if (!selectedKB || !hasIndexingDocuments) return;
    const interval = setInterval(async () => {
      try {
        const docs = await knowledgeApi.listDocuments(selectedKB.id);
        setDocuments(docs);
      } catch (err) {
        console.error("轮询文档状态失败:", err);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [selectedKB, hasIndexingDocuments]);

  const content = isSplitLayout ? (
    <div className="grid min-h-0 flex-1 xl:grid-cols-[340px_minmax(0,1fr)]">
      <div className="flex min-h-[360px] flex-col border-b border-border/80 bg-muted/60 xl:min-h-0 xl:border-b-0 xl:border-r">
        <KBListPane
          listTitle={listTitle}
          listDescription={listDescription}
          knowledgeBases={knowledgeBases}
          isLoadingList={isLoadingList}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          filteredKBs={filteredKBs}
          scopedKnowledgeBases={scopedKnowledgeBases}
          selectedKB={selectedKB}
          onSelectKB={(kb) => void openDetail(kb)}
          onDeleteKB={handleDeleteKB}
          allowCreate={allowCreate}
          onCreate={openCreateDialog}
        />
      </div>
      <div className="flex min-h-[480px] min-w-0 flex-col bg-white">
        {selectedKB ? (
          <KBDetailPane
            selectedKB={selectedKB}
            documents={documents}
            isLoadingDocs={isLoadingDocs}
            documentChunkCount={documentChunkCount}
            isSplitLayout={isSplitLayout}
            embeddingModels={embeddingModels}
            defaultEmbeddingModelId={defaultEmbeddingModelId}
            isLoadingModels={isLoadingModels}
            onBack={backToList}
            onUpload={openUploadDialog}
            onQuery={() => setIsQueryOpen(true)}
            onDeleteDoc={handleDeleteDoc}
            onSaveConfig={handleUpdateKBConfig}
          />
        ) : (
          <KBDetailEmpty />
        )}
      </div>
    </div>
  ) : !selectedKB ? (
    <KBListPane
      listTitle={listTitle}
      listDescription={listDescription}
      knowledgeBases={knowledgeBases}
      isLoadingList={isLoadingList}
      searchQuery={searchQuery}
      onSearchQueryChange={setSearchQuery}
      filteredKBs={filteredKBs}
      scopedKnowledgeBases={scopedKnowledgeBases}
      selectedKB={selectedKB}
      onSelectKB={(kb) => void openDetail(kb)}
      onDeleteKB={handleDeleteKB}
      allowCreate={allowCreate}
      onCreate={openCreateDialog}
    />
  ) : (
    <KBDetailPane
      selectedKB={selectedKB}
      documents={documents}
      isLoadingDocs={isLoadingDocs}
      documentChunkCount={documentChunkCount}
      isSplitLayout={isSplitLayout}
      embeddingModels={embeddingModels}
      defaultEmbeddingModelId={defaultEmbeddingModelId}
      isLoadingModels={isLoadingModels}
      onBack={backToList}
      onUpload={openUploadDialog}
      onQuery={() => setIsQueryOpen(true)}
      onDeleteDoc={handleDeleteDoc}
      onSaveConfig={handleUpdateKBConfig}
    />
  );

  return (
    <>
      {isPageMode ? (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl border border-border/90 bg-white/88 shadow-sm">
          {content}
        </div>
      ) : (
        <Dialog
          open={open}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) {
              onClose?.();
            }
          }}
        >
          <DialogContent
            className={cn(
              "flex h-[92vh] max-h-[92vh] flex-col gap-0 overflow-hidden p-0",
              isSplitLayout
                ? "w-[min(1280px,calc(100vw-2rem))] max-w-[min(1280px,calc(100vw-2rem))]"
                : "max-w-4xl",
            )}
          >
            {content}
          </DialogContent>
        </Dialog>
      )}

      <Suspense fallback={null}>
        <CreateDialog
          open={isCreateOpen}
          onOpenChange={setIsCreateOpen}
          createName={createName}
          onCreateNameChange={setCreateName}
          createDescription={createDescription}
          onCreateDescriptionChange={setCreateDescription}
          createEmbeddingModel={createEmbeddingModel}
          onCreateEmbeddingModelChange={setCreateEmbeddingModel}
          createSearchMode={createSearchMode}
          onCreateSearchModeChange={setCreateSearchMode}
          createChunkSize={createChunkSize}
          onCreateChunkSizeChange={setCreateChunkSize}
          createChunkOverlap={createChunkOverlap}
          onCreateChunkOverlapChange={setCreateChunkOverlap}
          embeddingModels={embeddingModels}
          isLoadingModels={isLoadingModels}
          isCreating={isCreating}
          onCreate={handleCreate}
        />
      </Suspense>

      <Suspense fallback={null}>
        <UploadDialog
          open={isUploadOpen}
          onOpenChange={setIsUploadOpen}
          documents={documents}
          uploadFiles={uploadFiles}
          uploadProgress={uploadProgress}
          uploadExtractionMode={uploadExtractionMode}
          onUploadExtractionModeChange={setUploadExtractionMode}
          uploadSearchMode={uploadSearchMode}
          onUploadSearchModeChange={setUploadSearchMode}
          uploadEmbeddingModel={uploadEmbeddingModel}
          onUploadEmbeddingModelChange={setUploadEmbeddingModel}
          uploadChunkSize={uploadChunkSize}
          onUploadChunkSizeChange={setUploadChunkSize}
          uploadChunkOverlap={uploadChunkOverlap}
          onUploadChunkOverlapChange={setUploadChunkOverlap}
          uploadResults={uploadResults}
          isUploading={isUploading}
          embeddingModels={embeddingModels}
          onFileSelect={handleFileSelect}
          onRemoveFile={handleRemoveFile}
          onUpload={handleUpload}
          onCancelUpload={handleCancelUpload}
          onClearFiles={() => setUploadFiles([])}
        />
      </Suspense>

      <Suspense fallback={null}>
        <QueryDialog
          open={isQueryOpen}
          onOpenChange={setIsQueryOpen}
          queryText={queryText}
          onQueryTextChange={setQueryText}
          querySearchMode={querySearchMode}
          onQuerySearchModeChange={setQuerySearchMode}
          queryResults={queryResults}
          isQuerying={isQuerying}
          onQuery={handleQuery}
        />
      </Suspense>

      <DeleteConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        deleteKind={deleteKind}
        isDeleting={isDeleting}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
}
