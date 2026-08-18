-- =============================================================================
-- ShipHub 생산관리 데이터베이스 스키마 설계
-- =============================================================================
--
-- [개념적 스키마] 엔티티와 관계 (ER)
--
--   ShipType(선종) --1:N--> Vessel(척) --1:N--> ProductionBlock(생산 블록)
--   Department(부서) --1:N--> ProductionBlock
--   ProcessStage(공정단계) --1:N--> ProductionBlock
--   Department(부서) --1:N--> ReviewSession(경량화 리뷰 세션 · ROI 실측 단위)
--
--   즉 ProductionBlock(사실/트랜잭션)이 Vessel/Department/ProcessStage 세 차원과
--   다대일로 연결되는 스타 스키마 구조이고, ReviewSession은 Department 차원에
--   연결되는 별도의 사실 테이블이다.
--
-- [논리적 스키마] 3NF 정규화 - 차원(dim_*) / 사실(fact_*) 테이블 분리
--
--   dim_ship_type(ship_type_id PK, name, complexity_multiplier)
--   dim_vessel(vessel_id PK, ship_type_id FK, vessel_code)
--   dim_department(department_id PK, name, hourly_cost_krw)
--   dim_process_stage(stage_id PK, name)
--   fact_production_block(block_id PK, vessel_id FK, stage_id FK, department_id FK, ...)
--   fact_review_session(session_id PK, department_id FK, month, ...)
--
--   정규화 근거: department/process_stage/ship_type을 원래 하나의 넓은 테이블에
--   문자열로 중복 저장하던 것(기존 SQLite 버전)을 차원 테이블로 분리해
--   갱신 이상(update anomaly, 예: 부서명 변경 시 수천 행을 다 고쳐야 하는 문제)과
--   저장 공간 낭비를 없앤다.
--
-- [물리적 스키마] 아래 실제 PostgreSQL DDL.
--
--   MariaDB에서 PostgreSQL로 이전했다. 논리적 스키마(테이블·컬럼·관계·뷰)는
--   그대로 두고 방언만 바꿨다 — 이전으로 설계가 흔들리지 않는다는 것이
--   정규화를 먼저 해 둔 덕이다. 바뀐 것은 다음 네 가지뿐이다.
--
--     AUTO_INCREMENT      -> GENERATED ALWAYS AS IDENTITY (표준 SQL)
--     ENUM(...) 인라인     -> CREATE TYPE ... AS ENUM (재사용 가능한 도메인 타입)
--     TINYINT / DATETIME  -> SMALLINT / TIMESTAMP
--     INDEX 인라인 선언     -> 별도 CREATE INDEX 문
--
--   문자셋 지정(utf8mb4)과 ENGINE=InnoDB 구문은 PostgreSQL에서 불필요하다.
--   PostgreSQL은 UTF-8이 기본이고 FK 제약이 엔진 선택과 무관하게 항상 동작한다.
--
--   데이터베이스 자체는 관리형 서비스(Neon 등)가 미리 만들어 주므로
--   CREATE DATABASE / USE 문은 두지 않는다. 이 스크립트는 이미 접속된
--   데이터베이스 위에서 실행한다.
--
-- =============================================================================

DROP VIEW IF EXISTS v_review_sessions;
DROP VIEW IF EXISTS v_production_records;
DROP TABLE IF EXISTS fact_review_session;
DROP TABLE IF EXISTS fact_production_block;
DROP TABLE IF EXISTS dim_vessel;
DROP TABLE IF EXISTS dim_ship_type;
DROP TABLE IF EXISTS dim_department;
DROP TABLE IF EXISTS dim_process_stage;
DROP TYPE IF EXISTS priority_t;
DROP TYPE IF EXISTS qa_status_t;

-- 우선순위와 QA 판정은 값 집합이 고정되어 있어 도메인 타입으로 선언한다.
-- 인라인 ENUM과 달리 여러 테이블에서 재사용할 수 있고, 값 추가도 ALTER TYPE으로 관리된다.
CREATE TYPE priority_t  AS ENUM ('High', 'Medium', 'Low');
CREATE TYPE qa_status_t AS ENUM ('합격', '불합격');

CREATE TABLE dim_ship_type (
    ship_type_id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                    VARCHAR(50) NOT NULL UNIQUE,
    complexity_multiplier   DECIMAL(4,2) NOT NULL,
    -- 대표 계약금액(원) - 실제 공시된 삼성중공업 수주 데이터 및 시장가 추정치 기반.
    -- 출처/방법론은 setup_postgres.py의 SHIP_TYPES 주석 참고.
    -- 3번 탭의 인도 지연 리스크(면책기간 소진율) 산출과 선종별 규모 비교에 사용.
    contract_value_krw      BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE dim_vessel (
    vessel_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ship_type_id    INT NOT NULL,
    vessel_code     VARCHAR(30) NOT NULL UNIQUE,
    CONSTRAINT fk_vessel_ship_type FOREIGN KEY (ship_type_id) REFERENCES dim_ship_type(ship_type_id)
);

CREATE TABLE dim_department (
    department_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name              VARCHAR(50) NOT NULL UNIQUE,
    hourly_cost_krw   INT NOT NULL
);

CREATE TABLE dim_process_stage (
    stage_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(30) NOT NULL UNIQUE
);

CREATE TABLE fact_production_block (
    block_id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vessel_id         INT NOT NULL,
    stage_id          INT NOT NULL,
    department_id     INT NOT NULL,
    block_name        VARCHAR(40) NOT NULL,
    priority          priority_t NOT NULL,
    triangle_count    INT NOT NULL,
    file_size_mb      DECIMAL(8,2) NULL,
    lod_level         SMALLINT NOT NULL,
    planned_days      INT NOT NULL,
    actual_days       INT NOT NULL,
    delay_days        DECIMAL(5,1) NOT NULL,
    qa_defect_count   INT NULL,
    qa_status         qa_status_t NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    CONSTRAINT fk_block_vessel     FOREIGN KEY (vessel_id) REFERENCES dim_vessel(vessel_id),
    CONSTRAINT fk_block_stage      FOREIGN KEY (stage_id) REFERENCES dim_process_stage(stage_id),
    CONSTRAINT fk_block_department FOREIGN KEY (department_id) REFERENCES dim_department(department_id)
);

-- PostgreSQL은 CREATE TABLE 안에 인덱스를 선언할 수 없어 별도 문으로 뺀다.
CREATE INDEX idx_block_created_at ON fact_production_block (created_at);
CREATE INDEX idx_block_department ON fact_production_block (department_id);

CREATE TABLE fact_review_session (
    session_id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department_id          INT NOT NULL,
    month                  CHAR(7) NOT NULL,
    review_type            VARCHAR(30) NOT NULL,
    triangle_count         INT NOT NULL,
    traditional_load_min   DECIMAL(6,2) NOT NULL,
    lightweight_load_sec   DECIMAL(6,2) NOT NULL,
    time_saved_min         DECIMAL(6,2) NOT NULL,
    cost_saved_krw         INT NOT NULL,
    CONSTRAINT fk_session_department FOREIGN KEY (department_id) REFERENCES dim_department(department_id)
);

CREATE INDEX idx_session_month ON fact_review_session (month);

-- 자주 쓰는 조인 뷰: 기존 SQLite 버전(production_records)과 동일한 평탄화(flat) 형태를
-- 재구성 - 전처리/ML 파이프라인 코드는 이 뷰 하나만 SELECT 하면 기존과 동일하게 동작한다.
-- 아래 두 뷰는 표준 SQL이라 MariaDB -> PostgreSQL 이전에도 한 글자도 바뀌지 않았다.
CREATE OR REPLACE VIEW v_production_records AS
SELECT
    b.block_id,
    st.name            AS ship_type,
    st.contract_value_krw,
    v.vessel_code      AS vessel_id,
    b.block_name,
    ps.name            AS process_stage,
    d.name             AS department,
    b.priority,
    b.triangle_count,
    b.file_size_mb,
    b.lod_level,
    b.planned_days,
    b.actual_days,
    b.delay_days,
    b.qa_defect_count,
    b.qa_status,
    b.created_at
FROM fact_production_block b
JOIN dim_vessel v         ON v.vessel_id = b.vessel_id
JOIN dim_ship_type st     ON st.ship_type_id = v.ship_type_id
JOIN dim_process_stage ps ON ps.stage_id = b.stage_id
JOIN dim_department d     ON d.department_id = b.department_id;

CREATE OR REPLACE VIEW v_review_sessions AS
SELECT
    s.session_id,
    d.name AS department,
    s.month,
    s.review_type,
    s.triangle_count,
    s.traditional_load_min,
    s.lightweight_load_sec,
    s.time_saved_min,
    d.hourly_cost_krw,
    s.cost_saved_krw
FROM fact_review_session s
JOIN dim_department d ON d.department_id = s.department_id;
