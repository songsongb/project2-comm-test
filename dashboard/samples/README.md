# 샘플 출처

`synthetic_demo.jsonl`은 `generate_demo.py`로 생성한 **합성 테스트 로그**입니다. 실제 수집 로그는 이 디렉터리에 제공되지 않았습니다. 6 MODE/LOAD 조건, PLOT, 유효/무효 TRIAL, Hub 상태·장애 이벤트, 명시적 TRACE_GAP을 포함합니다. 물리 측정이나 DMA 성능 증거가 아닙니다.

재생성:

```bash
python dashboard/samples/generate_demo.py
```

JSONL의 각 행에는 `received_at`(시간대가 있는 PC 수신 시각), `device`(window/door/hub/uno), `port`, `source`, `raw`가 필요합니다. 실제 로그는 `source=live`, 합성 자료는 `source=synthetic`으로 저장합니다. 원본 export는 파싱 결과 등 부가 필드를 포함해도 재생 가능합니다. 재생 시 ID·ingested_at은 새로 만들고 원래 PC 수신 시각과 raw는 유지합니다. 실제 재생 자료는 `replay-live`, 합성 재생은 `replay-synthetic`입니다.

직접 만든 fixture는 실제 펌웨어가 출력하지 않는 이벤트를 실제 로그로 표시하지 마세요. 잘못된 필드/자료형/상태/중복 행 등은 tests/에서 명시적으로 생성해 거부 동작을 확인합니다.
