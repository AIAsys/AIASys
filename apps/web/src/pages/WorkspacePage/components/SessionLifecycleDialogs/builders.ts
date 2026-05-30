import type {
  SessionConversationArchiveBatch,
  SessionExecutionMaintenanceMarker,
  SessionExecutionRecord,
  SessionHistoryMessage,
} from "../../types";
import type { ConversationHistoryBatch, ExecutionRecordSegment } from "./types";
import { getExecutionRecordTime, parseIsoTimestamp } from "./formatters";

export function buildConversationHistoryBatches(
  currentMessages: SessionHistoryMessage[],
  archivedBatches: SessionConversationArchiveBatch[],
): ConversationHistoryBatch[] {
  const historicalBatches = [...archivedBatches]
    .sort(
      (left, right) =>
        parseIsoTimestamp(right.archived_at) - parseIsoTimestamp(left.archived_at),
    )
    .map((batch) => ({
      id: batch.batch_id,
      isCurrent: false,
      occurredAt: batch.archived_at,
      label: batch.label || "较早对话记录",
      description: batch.description || "以下为较早阶段保留的对话记录。",
      messages: batch.messages || [],
    }))
    .filter((batch) => batch.messages.length > 0);

  return [
    {
      id: "current",
      isCurrent: true,
      label: "当前会话",
      description: "仅展示当前清理边界之后仍属于活跃阶段的会话内容。",
      messages: currentMessages,
    },
    ...historicalBatches,
  ];
}

export function buildExecutionRecordSegments(
  records: SessionExecutionRecord[],
  markers: SessionExecutionMaintenanceMarker[],
): ExecutionRecordSegment[] {
  const sortedRecords = [...records].sort(
    (left, right) => getExecutionRecordTime(right) - getExecutionRecordTime(left),
  );
  const sortedMarkers = [...markers].sort(
    (left, right) => parseIsoTimestamp(right.occurred_at) - parseIsoTimestamp(left.occurred_at),
  );

  if (sortedMarkers.length === 0) {
    return [{ id: "current", isCurrent: true, records: sortedRecords }];
  }

  const segments: ExecutionRecordSegment[] = [];
  const latestMarkerTime = parseIsoTimestamp(sortedMarkers[0]?.occurred_at);

  segments.push({
    id: "current",
    isCurrent: true,
    records: sortedRecords.filter((record) => getExecutionRecordTime(record) > latestMarkerTime),
  });

  for (let index = 0; index < sortedMarkers.length; index += 1) {
    const marker = sortedMarkers[index];
    const upperBound = parseIsoTimestamp(marker.occurred_at);
    const nextMarker = sortedMarkers[index + 1];
    const lowerBound = nextMarker
      ? parseIsoTimestamp(nextMarker.occurred_at)
      : Number.NEGATIVE_INFINITY;

    const segmentRecords = sortedRecords.filter((record) => {
      const recordTime = getExecutionRecordTime(record);
      return recordTime <= upperBound && recordTime > lowerBound;
    });

    if (segmentRecords.length === 0) continue;

    segments.push({
      id: marker.marker_id,
      isCurrent: false,
      marker,
      records: segmentRecords,
    });
  }

  return segments;
}
