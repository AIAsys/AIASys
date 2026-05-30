import { useCallback, useMemo } from "react";
import type { TaskState } from "@/hooks/useMultiTaskEventStream";

interface UseCodeExecutorViewStateProps {
  taskList: TaskState[];
  selectedTaskId: string | undefined;
  selectTask: (taskId: string) => void;
  setIsRightSidebarOpen: (open: boolean) => void;
  setUserClosedSidebar: (closed: boolean) => void;
}

export function useCodeExecutorViewState({
  taskList,
  selectedTaskId,
  selectTask,
  setIsRightSidebarOpen,
  setUserClosedSidebar,
}: UseCodeExecutorViewStateProps) {
  const handleViewExecutionSpace = useCallback(() => {
    setIsRightSidebarOpen(true);
    setUserClosedSidebar(false);
  }, [setIsRightSidebarOpen, setUserClosedSidebar]);

  const handleWorkerClick = useCallback(
    (workerName: string) => {
      // 使用 worker:${workerName} 格式作为 taskId
      selectTask(`worker:${workerName}`);
      setIsRightSidebarOpen(true);
      setUserClosedSidebar(false);
    },
    [selectTask, setIsRightSidebarOpen, setUserClosedSidebar],
  );
  
  // 处理 Sub Agent 点击 - 使用 tool_call_id 作为 taskId
  const handleSubAgentClick = useCallback(
    (toolCallId: string) => {
      selectTask(toolCallId);
      setIsRightSidebarOpen(true);
      setUserClosedSidebar(false);
    },
    [selectTask, setIsRightSidebarOpen, setUserClosedSidebar],
  );

  const workerTaskList = useMemo(
    () => taskList.filter((task) => task.taskId !== "host" || task.events.length > 0),
    [taskList],
  );

  const selectedTaskState = useMemo(() => {
    if (
      selectedTaskId &&
      workerTaskList.some((task) => task.taskId === selectedTaskId)
    ) {
      return {
        currentSelectedTask: workerTaskList.find(
          (task) => task.taskId === selectedTaskId,
        ),
        currentSelectedTaskId: selectedTaskId,
      };
    }

    if (workerTaskList.length > 0) {
      return {
        currentSelectedTask: workerTaskList[0],
        currentSelectedTaskId: workerTaskList[0].taskId,
      };
    }

    return {
      currentSelectedTask: undefined,
      currentSelectedTaskId: selectedTaskId,
    };
  }, [selectedTaskId, workerTaskList]);

  return {
    workerTaskList,
    currentSelectedTask: selectedTaskState.currentSelectedTask,
    currentSelectedTaskId: selectedTaskState.currentSelectedTaskId,
    handleViewExecutionSpace,
    handleWorkerClick,
    handleSubAgentClick,
  };
}
