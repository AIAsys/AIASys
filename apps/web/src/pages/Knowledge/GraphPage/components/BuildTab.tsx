import { RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { GraphExtractionMode, AddGraphDocumentResponse, UploadGraphDocumentResponse } from "@/types/graphrag";
import { UploadForm } from "./UploadForm";
import { TextForm } from "./TextForm";
import { ResultsPanel } from "./ResultsPanel";

interface BuildTabProps {
  buildTab: "upload" | "text" | "results";
  isRefreshing: boolean;
  // Upload form
  uploadFile: File | null;
  uploadDocumentId: string;
  uploadExtractionMode: GraphExtractionMode;
  uploadResolveEntities: boolean;
  isUploadingDocument: boolean;
  uploadError: string | null;
  uploadResult: UploadGraphDocumentResponse | null;
  // Text form
  documentText: string;
  documentId: string;
  resolveEntities: boolean;
  isSubmittingDocument: boolean;
  documentError: string | null;
  documentResult: AddGraphDocumentResponse | null;
  // Callbacks
  onBuildTabChange: (tab: "upload" | "text" | "results") => void;
  onRefresh: () => void;
  // Upload callbacks
  onUploadFileChange: (file: File | null) => void;
  onUploadIdChange: (id: string) => void;
  onUploadExtractionModeChange: (mode: GraphExtractionMode) => void;
  onUploadResolveEntitiesChange: (value: boolean) => void;
  onUploadSubmit: (e: React.FormEvent) => void;
  // Text callbacks
  onTextChange: (text: string) => void;
  onTextIdChange: (id: string) => void;
  onTextResolveEntitiesChange: (value: boolean) => void;
  onTextSubmit: (e: React.FormEvent) => void;
  // Results callbacks
  onOpenUpload: () => void;
  onOpenText: () => void;
}

export function BuildTab({
  buildTab,
  isRefreshing,
  uploadFile,
  uploadDocumentId,
  uploadExtractionMode,
  uploadResolveEntities,
  isUploadingDocument,
  uploadError,
  uploadResult,
  documentText,
  documentId,
  resolveEntities,
  isSubmittingDocument,
  documentError,
  documentResult,
  onBuildTabChange,
  onRefresh,
  onUploadFileChange,
  onUploadIdChange,
  onUploadExtractionModeChange,
  onUploadResolveEntitiesChange,
  onUploadSubmit,
  onTextChange,
  onTextIdChange,
  onTextResolveEntitiesChange,
  onTextSubmit,
  onOpenUpload,
  onOpenText,
}: BuildTabProps) {
  return (
    <Card className="self-start border-border/90 shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="text-xl text-foreground">
            文档构图工作台
          </CardTitle>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            先把材料构进图谱，再去看图和问答会更顺。这里同时提供文件构图和文本构图两种入口；成功构图后会刷新上方总览图。
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          disabled={isRefreshing}
          onClick={onRefresh}
        >
          <RefreshCw
            className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
          />
          刷新概览
        </Button>
      </CardHeader>
      <CardContent>
        <Tabs
          value={buildTab}
          onValueChange={(value) => onBuildTabChange(value as "upload" | "text" | "results")}
          className="space-y-6"
        >
          <div className="rounded-2xl border border-border bg-muted/80 p-2">
            <TabsList className="grid h-auto w-full grid-cols-3 rounded-xl bg-transparent p-0">
              <TabsTrigger value="upload" className="rounded-lg py-2.5">
                文件构图
              </TabsTrigger>
              <TabsTrigger value="text" className="rounded-lg py-2.5">
                文本构图
              </TabsTrigger>
              <TabsTrigger value="results" className="rounded-lg py-2.5">
                最近结果
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="upload" className="mt-0">
            <UploadForm
              uploadFile={uploadFile}
              uploadDocumentId={uploadDocumentId}
              uploadExtractionMode={uploadExtractionMode}
              uploadResolveEntities={uploadResolveEntities}
              isUploadingDocument={isUploadingDocument}
              uploadError={uploadError}
              uploadResult={uploadResult}
              onFileChange={onUploadFileChange}
              onDocumentIdChange={onUploadIdChange}
              onExtractionModeChange={onUploadExtractionModeChange}
              onResolveEntitiesChange={onUploadResolveEntitiesChange}
              onSubmit={onUploadSubmit}
            />
          </TabsContent>

          <TabsContent value="text" className="mt-0">
            <TextForm
              documentText={documentText}
              documentId={documentId}
              resolveEntities={resolveEntities}
              isSubmittingDocument={isSubmittingDocument}
              documentError={documentError}
              documentResult={documentResult}
              onTextChange={onTextChange}
              onIdChange={onTextIdChange}
              onResolveEntitiesChange={onTextResolveEntitiesChange}
              onSubmit={onTextSubmit}
            />
          </TabsContent>

          <TabsContent value="results" className="mt-0">
            <ResultsPanel
              uploadResult={uploadResult}
              documentResult={documentResult}
              onOpenUpload={onOpenUpload}
              onOpenText={onOpenText}
            />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
