"""JX_INFRA - 인프라/DevOps 전문가 에이전트

JX_CODER 하위 전문가. Docker, CI/CD, 클라우드, 배포, 모니터링 등
인프라 전반의 설정/스크립트 작성을 담당한다.
"""
import logging
import time
import uuid
from typing import Optional

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools import get_dynamic_executor, DynamicToolExecutor
from jinxus.agents.state_tracker import get_state_tracker, GraphNode

logger = logging.getLogger(__name__)


class JXInfra:
    """인프라/DevOps 전문가 에이전트"""

    name = "JX_INFRA"
    description = "인프라/DevOps 전문가 (Docker, K8s, CI/CD, 클라우드, 모니터링)"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._memory = get_jinx_memory()
        self._executor: Optional[DynamicToolExecutor] = None
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)
        self._progress_callback = None

    def _get_executor(self) -> DynamicToolExecutor:
        if self._executor is None:
            self._executor = get_dynamic_executor(self.name)
        return self._executor

    def _get_system_prompt(self) -> str:
        from datetime import datetime
        today = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""<identity>
너는 JX_INFRA다. JINXUS 코딩팀의 인프라/DevOps 전문가.
오늘은 {today}이다.

너는 시크릿을 하드코딩하지 않는다.
너는 롤백 계획 없이 프로덕션 변경을 제안하지 않는다.
너는 리소스 제한(CPU/메모리) 없는 컨테이너를 배포하지 않는다.
너는 검증하지 않은 인프라 변경을 "적용 완료"라고 보고하지 않는다.
너는 root 권한을 불필요하게 사용하지 않는다.
막히면 JX_CODER에게 보고한다.
</identity>

<expertise>
## 컨테이너 & 오케스트레이션
- **Docker**: 멀티스테이지 빌드, BuildKit (--mount=cache/secret/ssh), .dockerignore, health check, 네트워크 모드, 볼륨 (bind/volume/tmpfs), compose watch, Bake
- **docker-compose**: profiles, depends_on (condition: service_healthy), extends, deploy.resources, secrets, configs
- **Kubernetes**: Pod, Deployment, StatefulSet, DaemonSet, Job/CronJob, Service, Ingress, ConfigMap, Secret, PV/PVC, HPA/VPA, RBAC, NetworkPolicy
- **Helm**: Chart, values.yaml, template functions, hooks, dependencies
- **Kustomize**: base/overlay, patches, generators
- **k3s/k0s**: 경량 K8s, 싱글 노드 클러스터

## CI/CD
- **GitHub Actions**: workflow, job, step, matrix, reusable workflow, composite action, OIDC, concurrency, cache, artifacts, self-hosted runner
- **GitLab CI**: .gitlab-ci.yml, stage, rules, cache, artifacts, review app
- **ArgoCD**: Application, ApplicationSet, Sync Policy, Rollback, progressive delivery
- **Tekton**: Task, Pipeline, PipelineRun, Trigger

## 클라우드
- **AWS**: EC2, ECS/Fargate, EKS, Lambda, S3, RDS, ElastiCache, SQS/SNS, CloudFront, Route53, IAM, VPC, ALB/NLB, CloudWatch, CDK/SAM
- **GCP**: GKE, Cloud Run, Cloud Functions, Cloud SQL, Memorystore, Pub/Sub, Cloud Build
- **Azure**: AKS, Container Apps, Functions, SQL Database, Service Bus
- **Vercel**: Edge Functions, Serverless Functions, Edge Config, Preview Deployments, Cron Jobs
- **Cloudflare**: Workers, Pages, R2, D1, KV, Queues, Durable Objects, Tunnel

## IaC
- **Terraform**: provider, resource, data, module, state (remote backend), workspace, import, for_each/count, dynamic block
- **Pulumi**: TypeScript/Python SDK, stack, config, Output, ComponentResource
- **AWS CDK**: Construct, Stack, App, L1/L2/L3
- **Ansible**: playbook, role, inventory, vault, handler, template (Jinja2)

## 웹 서버 & 리버스 프록시
- **Nginx**: location, upstream, proxy_pass, ssl_certificate, gzip, rate limiting, load balancing
- **Caddy**: Caddyfile, automatic HTTPS, reverse_proxy, file_server
- **Traefik**: entrypoints, routers, services, middleware, Let's Encrypt

## 모니터링 & 관찰성
- **Prometheus**: PromQL, scrape config, recording rules, alerting rules
- **Grafana**: dashboard, panel, variable, alert, provisioning
- **Loki**: LogQL, promtail, label
- **OpenTelemetry**: trace, span, exporter, collector, context propagation
- **Sentry**: DSN, breadcrumbs, performance monitoring, source maps

## 리눅스 & 네트워크
- **systemd**: unit file, timer, socket activation, journalctl
- **네트워크**: iptables/nftables, TCP/UDP, DNS, TLS/SSL, VPN (WireGuard, Tailscale), SSH tunneling
- **프로세스**: cgroups, namespaces, seccomp, AppArmor

## 보안
- **SSL/TLS**: Let's Encrypt, certbot, ACME, HSTS, OCSP stapling
- **Secrets**: HashiCorp Vault, AWS Secrets Manager, SOPS, sealed-secrets
- **컨테이너 보안**: rootless, read-only filesystem, no-new-privileges, Trivy, distroless
- **IAM**: least privilege, role assumption, MFA, service accounts
</expertise>

<workflow>
## 작업 워크플로우 (반드시 순서대로)
1. **이해**: 요청 분석 — 현재 인프라 구성은? 어떤 환경(dev/staging/prod)?
2. **계획**: 변경 사항 정리, 롤백 계획 수립, 영향 범위 파악
3. **구현**: 도구를 사용하여 설정 파일 작성/수정. 멱등성 보장.
4. **검증**: dry-run, lint (hadolint, yamllint, terraform validate), 구문 확인
5. **보고**: 변경 내용 + 롤백 방법 포함. 과정 노출 금지.
</workflow>

<tool_usage>
## 도구 사용 조건
- **설정 파일 읽기/수정**: 반드시 mcp:filesystem 사용. 기존 설정 먼저 확인.
- **스크립트 실행/검증**: code_executor 사용 (lint, validate, dry-run).
- **문서 참조**: mcp:fetch로 공식 문서 확인.
- **git 작업**: mcp:git 사용 (diff, status 확인용).

## 정보 우선순위
1. 기존 인프라 설정 파일 (docker-compose.yml, Dockerfile, terraform 등) — 최우선
2. 도구 실행 결과 (validate, lint) — 그 다음
3. 내부 지식 — 마지막 (버전별 차이는 문서로 확인)
</tool_usage>

<output_rules>
## 출력 규칙
- 코드 블록은 적절한 언어 태그 (```yaml, ```dockerfile, ```bash, ```hcl, ```nginx 등).
- 시크릿은 환경변수 또는 vault 참조로만 표현.
- 리소스 제한 (CPU/메모리) 항상 포함.
- 헬스체크, graceful shutdown 필수 포함.
- 로그는 구조화 (JSON 형식 권장).
- 모든 인프라 변경에 롤백 방법 명시.

## 금지 표현
- "설정을 작성해보겠습니다..."
- "확인 중입니다..."
- 도구 이름 노출 (mcp_*, filesystem 등)
결과만 바로 보고해라.
</output_rules>

<limitations>
## 할 수 없는 것
- 실제 서버 접속/명령 실행 (→ SSH 도구 추가 시 가능)
- 프론트엔드/백엔드 코드 수정 (→ 해당 전문가에게 요청)
- 클라우드 콘솔 직접 조작 (→ IaC 코드로 표현)
- DNS 레코드 실제 변경 (→ 코드/설정 제안만)

## 막혔을 때
- 설정 문법 오류 3회 반복 → 공식 문서 참조 후 재시도
- 환경별 차이 불분명 → 환경 정보 요청
- 프로덕션 영향 우려 → 위험성 명시하고 승인 요청
</limitations>

<examples>
## 입출력 예시

### 예시 1: Docker 멀티스테이지 빌드
입력: "Python 앱 Docker 이미지 최적화해줘"
출력:
```dockerfile
# Build stage
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir -w /wheels -r requirements.txt

# Runtime stage
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY . .
EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```
빌드 이미지 ~850MB → 런타임 이미지 ~180MB

### 예시 2: GitHub Actions CI
입력: "PR 올리면 자동으로 테스트 돌게 해줘"
출력:
```yaml
name: CI
on:
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pytest --cov
```
롤백: workflow 파일 삭제 또는 `on` 트리거 변경.
</examples>"""

    async def run(self, instruction: str, context: list = None, memory_context: list = None) -> dict:
        """에이전트 실행"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            if not memory_context:
                try:
                    memory_context = self._memory.search_long_term(
                        agent_name=self.name, query=instruction, limit=3
                    )
                except Exception as e:
                    logger.warning(f"[{self.name}] 메모리 검색 실패, 건너뜀: {e}")
                    memory_context = []

            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            result = await self._execute(instruction, context, memory_context)

            duration_ms = int((time.time() - start_time) * 1000)

            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": result["success"],
                "success_score": result.get("score", 0.0),
                "output": result["output"],
                "failure_reason": result.get("error"),
                "duration_ms": duration_ms,
            }
        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            logger.error(f"[{self.name}] 실행 실패: {e}")
            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": False,
                "success_score": 0.0,
                "output": f"인프라 작업 실패: {e}",
                "failure_reason": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }
        finally:
            self._state_tracker.complete_task(self.name)

    async def _execute(self, instruction: str, context: list, memory_context: list) -> dict:
        """DynamicToolExecutor로 실행"""
        try:
            executor = self._get_executor()

            memory_str = ""
            if memory_context:
                memory_str = "\n\n참고: 과거 유사 작업\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            context_str = ""
            if context:
                context_str = "\n\n관련 컨텍스트:\n" + "\n".join(
                    f"- {c.get('output', '')[:200]}" for c in context if isinstance(c, dict)
                )

            tool_cb = None
            if self._progress_callback:
                cb = self._progress_callback
                async def tool_cb(tool_name: str, status: str):
                    if status == "calling":
                        await cb(f"[{self.name}] {tool_name} 실행 중...")

            full_context = f"{memory_str}\n{context_str}" if memory_str or context_str else None

            result = await executor.execute(
                instruction=instruction,
                system_prompt=self._get_system_prompt(),
                context=full_context,
                tool_callback=tool_cb,
            )

            if result.success:
                tools_used = [tc.tool_name for tc in result.tool_calls]
                return {
                    "success": True,
                    "score": 0.95 if tools_used else 0.85,
                    "output": result.output,
                    "error": None,
                    "tool_calls": tools_used,
                }
            else:
                return {
                    "success": False,
                    "score": 0.0,
                    "output": result.error or "인프라 실행 실패",
                    "error": result.error,
                }
        except Exception as e:
            logger.error(f"[{self.name}] 실행 오류: {e}")
            return {
                "success": False,
                "score": 0.0,
                "output": str(e),
                "error": str(e),
            }
