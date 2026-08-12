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
-- [물리적 스키마] 아래 실제 MariaDB DDL. InnoDB(FK 제약 지원) + utf8mb4.
--
-- =============================================================================

CREATE DATABASE IF NOT EXISTS shiphub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE shiphub;

DROP TABLE IF EXISTS fact_review_session;
DROP TABLE IF EXISTS fact_production_block;
DROP TABLE IF EXISTS dim_vessel;
DROP TABLE IF EXISTS dim_ship_type;
DROP TABLE IF EXISTS dim_department;
DROP TABLE IF EXISTS dim_process_stage;

CREATE TABLE dim_ship_type (
    ship_type_id            INT AUTO_INCREMENT PRIMARY KEY,
    name                    VARCHAR(50) NOT NULL UNIQUE,
    complexity_multiplier   DECIMAL(4,2) NOT NULL,
    -- 대표 계약금액(원) - 실제 공시된 삼성중공업 수주 데이터 및 시장가 추정치 기반.
    -- 출처/방법론은 setup_mariadb.py의 SHIP_TYPES 주석 참고. 지체상금(지연 방지 가치) 산출에 사용.
    contract_value_krw     BIGINT NOT NULL DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE dim_vessel (
    vessel_id       INT AUTO_INCREMENT PRIMARY KEY,
    ship_type_id    INT NOT NULL,
    vessel_code     VARCHAR(30) NOT NULL UNIQUE,
    CONSTRAINT fk_vessel_ship_type FOREIGN KEY (ship_type_id) REFERENCES dim_ship_type(ship_type_id)
) ENGINE=InnoDB;

CREATE TABLE dim_department (
    department_id    INT AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(50) NOT NULL UNIQUE,
    hourly_cost_krw   INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE dim_process_stage (
    stage_id    INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(30) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE fact_production_block (
    block_id          INT AUTO_INCREMENT PRIMARY KEY,
    vessel_id         INT NOT NULL,
    stage_id          INT NOT NULL,
    department_id     INT NOT NULL,
    block_name        VARCHAR(40) NOT NULL,
    priority          ENUM('High','Medium','Low') NOT NULL,
    triangle_count    INT NOT NULL,
    file_size_mb      DECIMAL(8,2) NULL,
    lod_level         TINYINT NOT NULL,
    planned_days      INT NOT NULL,
    actual_days       INT NOT NULL,
    delay_days        DECIMAL(5,1) NOT NULL,
    qa_defect_count   INT NULL,
    qa_status         ENUM('합격','불합격') NOT NULL,
    created_at        DATETIME NOT NULL,
    CONSTRAINT fk_block_vessel     FOREIGN KEY (vessel_id) REFERENCES dim_vessel(vessel_id),
    CONSTRAINT fk_block_stage      FOREIGN KEY (stage_id) REFERENCES dim_process_stage(stage_id),
    CONSTRAINT fk_block_department FOREIGN KEY (department_id) REFERENCES dim_department(department_id),
    INDEX idx_block_created_at (created_at),
    INDEX idx_block_department (department_id)
) ENGINE=InnoDB;

CREATE TABLE fact_review_session (
    session_id             INT AUTO_INCREMENT PRIMARY KEY,
    department_id           INT NOT NULL,
    month                    CHAR(7) NOT NULL,
    review_type              VARCHAR(30) NOT NULL,
    triangle_count            INT NOT NULL,
    traditional_load_min     DECIMAL(6,2) NOT NULL,
    lightweight_load_sec     DECIMAL(6,2) NOT NULL,
    time_saved_min           DECIMAL(6,2) NOT NULL,
    cost_saved_krw           INT NOT NULL,
    CONSTRAINT fk_session_department FOREIGN KEY (department_id) REFERENCES dim_department(department_id),
    INDEX idx_session_month (month)
) ENGINE=InnoDB;

-- 자주 쓰는 조인 뷰: 기존 SQLite 버전(production_records)과 동일한 평탄화(flat) 형태를
-- 재구성 - 전처리/ML 파이프라인 코드는 이 뷰 하나만 SELECT 하면 기존과 동일하게 동작한다.
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
JOIN dim_vessel v        ON v.vessel_id = b.vessel_id
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
