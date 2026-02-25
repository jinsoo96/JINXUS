## 진수의 명령
{user_input}

## 참고: 과거 유사 작업
{memory_context}

## 가용 에이전트
JX_CODER, JX_RESEARCHER, JX_WRITER, JX_ANALYST, JX_OPS

## 지시
위 명령을 분석하고 다음 JSON으로만 응답해:

```json
{
  "subtasks": [
    {
      "task_id": "sub_001",
      "assigned_agent": "JX_CODER",
      "instruction": "에이전트에게 전달할 구체적 지시",
      "depends_on": [],
      "priority": "normal"
    }
  ],
  "execution_mode": "parallel | sequential | mixed",
  "brief_plan": "한 줄 실행 계획"
}
```

판단 기준:
- 서브태스크들 간 의존성 없으면 parallel
- 앞 결과가 뒤 입력으로 필요하면 depends_on 명시
- 단순 명령이면 subtasks 1개
