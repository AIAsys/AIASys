---
name: agent-state-machine-reference
description: Strict state machine patterns for agent runtime lifecycle management in AIASys.
---

# 状态流设计

设计清晰、可维护的状态流转系统，用于复杂 UI 交互和业务流程。

---

## 何时使用状态流

## 严格状态机设计


当需要严格的状态控制时使用：

```typescript
// 状态定义
enum SessionState {
  IDLE = 'idle',
  INITIALIZING = 'initializing',
  RUNNING = 'running',
  PAUSED = 'paused',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

// 事件定义
enum SessionEvent {
  START = 'start',
  INIT_COMPLETE = 'init_complete',
  PAUSE = 'pause',
  RESUME = 'resume',
  COMPLETE = 'complete',
  FAIL = 'fail',
  CANCEL = 'cancel'
}

// 状态转换表
const TRANSITIONS: Record<SessionState, Record<SessionEvent, SessionState>> = {
  [SessionState.IDLE]: {
    [SessionEvent.START]: SessionState.INITIALIZING
  },
  [SessionState.INITIALIZING]: {
    [SessionEvent.INIT_COMPLETE]: SessionState.RUNNING,
    [SessionEvent.FAIL]: SessionState.FAILED,
    [SessionEvent.CANCEL]: SessionState.CANCELLED
  },
  [SessionState.RUNNING]: {
    [SessionEvent.PAUSE]: SessionState.PAUSED,
    [SessionEvent.COMPLETE]: SessionState.COMPLETED,
    [SessionEvent.FAIL]: SessionState.FAILED,
    [SessionEvent.CANCEL]: SessionState.CANCELLED
  },
  [SessionState.PAUSED]: {
    [SessionEvent.RESUME]: SessionState.RUNNING,
    [SessionEvent.CANCEL]: SessionState.CANCELLED
  },
  // 终止状态无转换
  [SessionState.COMPLETED]: {},
  [SessionState.FAILED]: {},
  [SessionState.CANCELLED]: {}
};

// 状态机类
class SessionStateMachine {
  private state: SessionState = SessionState.IDLE;
  
  canTransition(event: SessionEvent): boolean {
    return event in TRANSITIONS[this.state];
  }
  
  transition(event: SessionEvent): SessionState {
    if (!this.canTransition(event)) {
      throw new Error(
        `Invalid transition: ${this.state} -> ${event}`
      );
    }
    this.state = TRANSITIONS[this.state][event];
    return this.state;
  }
  
  getState(): SessionState {
    return this.state;
  }
}
```

---
