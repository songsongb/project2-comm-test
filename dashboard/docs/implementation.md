# 변경 내역과 요구사항 대응

신규 `dashboard/` 디렉터리만 추가했습니다. 기존 tracked 파일은 수정하지 않았으며 사용자 제공 펌웨어 6개는 미추적 상태를 유지합니다. 작업 브랜치 `feature/dashboard-llm`을 `feature/comm-smoke-test`의 `021eed5`에서 생성했습니다. 커밋·push·MCU 업로드는 수행하지 않았습니다.

## 단계별 구현

| 단계 | 결과 |
|---|---|
| Phase 1 | 포트 자동 열거/수동 역할 선택, 다중 수신, 장치별 파서, 상태/최신성, SQLite 원본, JSONL 재생, 자동 재연결 |
| Phase 2 | 실제 STAT 17개 숫자 필드, MCU interval 처리량, 관측 누락, 취득 IRQ, 사이클/시간 비율, MODE/LOAD별 통계, 안정화/경계 제외, 실험 저장/CSV |
| Sensor | PLOT 수동 계측 명령/5Hz 그래프, mic RMS·기준·임계값, TRACE markers/빈 구간/END 검증, 유효 TRIAL 성공률과 조건별 집계 |
| Phase 3 | 규칙 탐지, 쿨다운, 선택/자동 진단, 로컬 Ollama JSON Schema, evidence ID/값/명령 검증, 모델/timeout, 중복 방지·별도 스레드, 자연어 질문·이력 |
| Phase 4 | 8개 고정 허용 명령(읽기 2개/변경 6개), DISARMED/최신 상태 검사, CAL 환경 확인, 단일 승인, 전송 직전 재검사, ACK 매칭·후속 계측 검증·감사 이력 |
| Phase 5 | 파서·성능·세션·재생·가상 다중 포트·재연결·Ollama 실패/timeout·거부/무승인/중복·CAL 양노드·AppTest·Linux 실제 PySerial PTY 검증 |

MODE 0/1/2, LOAD 0/1, CAL은 변경 명령 6개입니다. STATUS/HELP를 제외한 arbitrary write API는 UI/LLM에 노출하지 않습니다. 수동 Window PLOT/PLOTOFF/TRACE는 별도의 고정 계측 명령이며 레이저/릴레이 동작이 아닙니다.

## 데이터와 실행 경로

```text
USB port worker × N → bounded PC record queue → parser → state / metrics / SQLite
                                                    → anomaly rules → diagnosis queue → Ollama

Streamlit rerun/fragment → singleton Runtime snapshot → five tabs
LLM actions enum → proposal → state/physical confirmations → explicit approval
                 → port writer queue → state recheck → fixed UART bytes
                 → matched hub result → fresh STATUS + sensor logs → audit record
```

PC 수신 시각은 UTC timezone-aware ISO 문자열, MCU ms는 장치별 독립 uint32입니다. BOOT/클록 역행을 감지하면 해당 장치 세션을 구분합니다. uint32 wrap과 지연 TRIAL은 재부팅과 구별합니다. 알림/진단에는 source를 넣고 실측과 합성을 통계에서도 분리합니다.

보존 버퍼는 원본 2000행, STAT 7200구간, PLOT 3000개, TRIAL 1000개, 이벤트 500개, TRACE 15개입니다. 전체 원본은 SQLite, 실험/진단/완료 TRACE/명령은 artifact로 지속 저장합니다. 전체 원본 streaming export CLI도 제공합니다. 디스크 자동 회전은 아직 없으며 장기 실행 후 백업이 필요합니다.

## 최종 질문에 대한 답

- **MCU 수정 없이 어디까지?** 최신 4보드 텍스트 로그 수집·재생, DMA 비교·실험, 센서/TRACE/TRIAL, Hub 상태·오류 규칙, LLM 가설 및 승인 명령·후속 검증을 PC에서 구현했습니다. MCU 재빌드·업로드는 필요 없습니다.
- **실제 측정 DMA 지표?** 현재 실측 로그가 제공되지 않아 실측 수치는 없습니다. 연결하면 pairs/skipped/acq_cycles/acq_permille/acq_irqs/mode/load/ready와 원본 필드를 수집합니다. 샘플 JSONL 값은 전부 합성입니다.
- **추가 계측?** UART ORE/FE/NE, DMA overrun/TE 원인별 카운터, 전체 CPU 사용률, 검출 지연, 실제 광학 pulse, 구간 elapsed/seq, HB age·pending·experiment 등. 구체적인 제안은 [분석 문서](firmware_analysis.md)에 있습니다.
- **LLM 진단?** 관측된 센서/보정/링크/명령/수집/프레임 오류/경보/실험 문제의 가능한 원인과 점검 절차입니다. 단일 SENSOR_FAULT로 ADC DMA 고장을 확정하지 않습니다. 입력 근거와 구조 검증이 실패하면 결과를 표시 가능한 사실로 승격하지 않습니다.
- **실행 가능한 복구?** 실제 Hub 연결 및 최신 DISARMED·두 센서 READY·유휴 확인 하에 MODE 0/1/2, LOAD 0/1, CAL. CAL은 물리 환경 확인 및 양노드 후속 로그 필요. 실제 하드웨어 명령 수행 자체는 미검증입니다. MCU가 전제 조건에 따라 거부할 수 있습니다.
- **차단한 동작?** ARM/DISARM, Uno LASER/TEST/STOP/DEMO, GPIO/레지스터, 리셋/재부팅/펌웨어 변경, Window TH 변경. LLM의 자연어는 시리얼로 전송하지 않습니다.

## 남은 제약

1. Windows 실제 COM/케이블/장시간 스트레스, 실제 4보드/DMA 우수성 실험, 실제 Ollama 모델 추론은 미검증입니다.
2. native browser 자동화 도구가 없어 브라우저 스크린샷/픽셀 확인은 수행하지 않았습니다. Streamlit AppTest로 모든 탭의 실제 생성과 synthetic 전체 데이터 렌더를 확인했습니다.
3. 현재 펌웨어 STATUS만으로 숨겨진 전제 조건을 완벽히 확인할 수 없어 물리 유휴 확인과 MCU 거부를 사용합니다. FAULT 중 CAL은 PC에서 보수적으로 차단합니다.
4. request ID가 없는 ACK 프로토콜은 외부 수동 명령과 완벽히 구별하지 못합니다. 동시에 다른 터미널/물리 제어에서 명령을 실행하지 않는 실험 절차가 필요합니다.
5. `verified`는 요청 상태의 후속 확인이며 근본 장애의 자동 해결 판정이 아닙니다. 실패/불명확은 자동 재시도하지 않습니다.
6. 포트 역할은 USB 정보만으로 확정할 수 없어 사용자 매핑입니다. Uno의 ARMED/DISARMED/센서 세부 상태는 출력되지 않아 추정하지 않습니다.
7. Streamlit 한 프로세스의 여러 브라우저는 수집기·입력 모드·승인 상태를 공유합니다. 승인자는 별도 로그인으로 식별하지 않고 명시적 승인/시각/근거를 기록합니다. 기본 실행은 loopback이며 다중 운영자 권한 시스템은 범위 밖입니다.
8. 재생은 원본 PC 시각을 보존하고 화면 최신성에는 현재 ingestion 시간을 사용합니다. 긴 파일은 업로드·스케줄링을 위해 메모리에 읽습니다. 재생 간격이 60초보다 크면 대기 60초로 제한하며 시간 그래프는 원래 PC/MCU 시간을 유지합니다.
