# OWL 2 RL 프로파일 메모

- 구현: `owlrl` 의 OWL-RL 규칙(전방 연쇄). `rdfs=True` 면 RDFS 규칙을 추가한다.
- 비일관성은 owlrl 이 폐포 그래프에 `err:ErrorMessage`(`http://www.daml.org/2002/03/agents/agent-ont#`) 노드로 남긴다.
  `reasoner.closure()` 가 이를 읽어 메시지로 바꾸고 폐포 그래프에서 지운다.
- 메시지 분류: `xsd:*` 쌍의 "have a common individual" 은 리터럴 값 공간 충돌(아티팩트), 그 밖은 논리적 비일관성이다.
- 파생 파일 형식: 맨 위 `# source-hash: sha256:<asserted 지문>` 주석, 본문에 파생 트리플과 `prov:Activity` 한 건.
  지문은 (asserted 파일 상대경로, 파일 sha256) 목록의 해시이며 `*.shapes.ttl`, `*.inferred.ttl` 은 제외한다.
- 알려진 한계: 합성(chain) 프로퍼티 공리, 복잡한 클래스 표현 기반 충족 가능성, 열린 세계 가정의 일부는 RL 로 못 다룬다.
